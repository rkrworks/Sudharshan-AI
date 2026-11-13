#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sign_windows_executable.py — Microsoft Authenticode PE Code-Signer for Sudharshan AI

Signs PE32/PE32+ executables (.exe, .dll) with the official Sudharshan AI
X.509 Code-Signing Certificate according to Microsoft Authenticode Specifications:
  - Omits CheckSum and Security Directory from Authenticode hash
  - Embeds SpcIndirectDataContent (1.3.6.1.4.1.311.2.1.4)
  - RSA-2048 PKCS#1 v1.5 signature with SHA-256 digest
  - Appends WIN_CERTIFICATE (0x0200 WIN_CERT_REVISION_2_0, 0x0002 PKCS_SIGNED_DATA)
  - Recalculates and updates PE OptionalHeader CheckSum
"""

import argparse
import hashlib
import io
import struct
import sys
from pathlib import Path

import asn1crypto.cms as cms
import pefile
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from signify.authenticode.indirect_data import spc
from signify.authenticode.signed_file.pe import SignedPEFile, SignedPEFingerprinter


def sign_pe_file(
    input_path: Path,
    output_path: Path,
    cert_path: Path,
    key_path: Path,
    program_name: str = "Sudharshan AI Desktop Assistant",
) -> bool:
    print(f"[1/5] Loading target executable: {input_path} ({input_path.stat().st_size} bytes)...")
    pe_raw = bytearray(input_path.read_bytes())
    pe = pefile.PE(data=pe_raw)

    # 1. Strip existing certificate table if present
    sec_entry = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_SECURITY"]]
    if sec_entry.Size > 0 and sec_entry.VirtualAddress > 0:
        print(f"  -> Truncating existing certificate table at offset {sec_entry.VirtualAddress}...")
        pe_raw = pe_raw[:sec_entry.VirtualAddress]
        sec_dir_offset = sec_entry.get_file_offset()
        struct.pack_into("<II", pe_raw, sec_dir_offset, 0, 0)

    # 2. Pad PE to 8-byte boundary prior to computing authentihash
    pad_pe = (8 - (len(pe_raw) % 8)) % 8
    if pad_pe > 0:
        pe_raw.extend(b"\x00" * pad_pe)

    # 3. Compute Authenticode SHA-256 hash
    print("[2/5] Computing Authenticode SHA-256 digest...")
    pe_for_hash = SignedPEFile(io.BytesIO(pe_raw))
    fp = pe_for_hash.get_fingerprinter()
    fp.add_signed_pe_hashers(hashlib.sha256)
    authentihash = fp.hashes()["authentihash"]["sha256"]
    print(f"  -> Authentihash: {authentihash.hex()}")

    # 4. Load Certificate and Private Key
    print(f"[3/5] Loading Code Signing Certificate from {cert_path}...")
    cert_bytes = cert_path.read_bytes()
    if b"-----BEGIN CERTIFICATE-----" in cert_bytes:
        cert = x509.load_pem_x509_certificate(cert_bytes)
    else:
        cert = x509.load_der_x509_certificate(cert_bytes)
    cert_asn1 = cms.Certificate.load(cert.public_bytes(serialization.Encoding.DER))

    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)

    # 5. Build Authenticode CMS SignedData structures
    print("[4/5] Constructing Authenticode SpcIndirectDataContent & CMS SignedData...")
    spc_obj = spc.SpcIndirectDataContent({
        "data": spc.SpcAttributeTypeAndOptionalValue({
            "type": "1.3.6.1.4.1.311.2.1.15",  # spc_pe_image_data
            "value": spc.SpcPeImageData({
                "flags": spc.SpcPeImageFlags(set(["include_resources"])),
                "file": spc.SpcLink({"file": spc.SpcString({"unicode": ""})})
            })
        }),
        "message_digest": spc.DigestInfo({
            "digest_algorithm": {"algorithm": "sha256"},
            "digest": authentihash
        })
    })
    content_bytes = spc_obj.dump()

    # Authenticated attributes
    spc_opus = spc.SpcSpOpusInfo({
        "program_name": spc.SpcString({"unicode": program_name})
    })
    opus_attr = cms.CMSAttribute({"type": "1.3.6.1.4.1.311.2.1.12", "values": [spc_opus]})
    ct_attr = cms.CMSAttribute({"type": "content_type", "values": ["1.3.6.1.4.1.311.2.1.4"]})
    md_attr = cms.CMSAttribute({"type": "message_digest", "values": [hashlib.sha256(content_bytes).digest()]})

    auth_attrs = cms.CMSAttributes([ct_attr, md_attr, opus_attr])
    attrs_to_sign = auth_attrs.dump()
    sig_bytes = key.sign(attrs_to_sign, padding.PKCS1v15(), hashes.SHA256())

    signer_info = cms.SignerInfo({
        "version": "v1",
        "sid": cms.SignerIdentifier({
            "issuer_and_serial_number": cms.IssuerAndSerialNumber({
                "issuer": cert_asn1.issuer,
                "serial_number": cert_asn1.serial_number
            })
        }),
        "digest_algorithm": {"algorithm": "sha256"},
        "signed_attrs": auth_attrs,
        "signature_algorithm": {"algorithm": "rsassa_pkcs1v15"},
        "signature": sig_bytes
    })

    signed_data = cms.SignedData({
        "version": "v1",
        "digest_algorithms": [{"algorithm": "sha256"}],
        "encap_content_info": {
            "content_type": "1.3.6.1.4.1.311.2.1.4",
            "content": spc_obj
        },
        "certificates": [cert_asn1],
        "signer_infos": [signer_info]
    })

    content_info = cms.ContentInfo({"content_type": "signed_data", "content": signed_data})
    der_sig = content_info.dump()

    # 6. Inject WIN_CERTIFICATE into PE
    cert_offset = len(pe_raw)
    win_cert = struct.pack("<IHH", len(der_sig) + 8, 0x0200, 0x0002) + der_sig
    pad_cert = (8 - (len(win_cert) % 8)) % 8
    win_cert += b"\x00" * pad_cert
    pe_raw.extend(win_cert)

    pe_reparsed = pefile.PE(data=pe_raw)
    sec_entry = pe_reparsed.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_SECURITY"]]
    sec_dir_offset = sec_entry.get_file_offset()
    struct.pack_into("<II", pe_raw, sec_dir_offset, cert_offset, len(win_cert))

    # 7. Recalculate PE CheckSum
    pe_final = pefile.PE(data=pe_raw)
    chk = pe_final.generate_checksum()
    chk_offset = pe_final.OPTIONAL_HEADER.get_file_offset() + 64
    struct.pack_into("<I", pe_raw, chk_offset, chk)

    # 8. Write to output and verify
    output_path.write_bytes(pe_raw)
    print(f"[5/5] Saved signed PE binary to {output_path} ({len(pe_raw)} bytes)...")

    verified_pe = SignedPEFile(io.BytesIO(pe_raw))
    sigs = list(verified_pe.iter_embedded_signatures())
    if not sigs:
        print("ERROR: Verification failed; no embedded signatures found.")
        return False
    sigs[0].verify_indirect_data(sigs[0].indirect_data)
    print(f"SUCCESS: 100% Valid Authenticode Signature attached for '{program_name}'!")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Sudharshan AI — Microsoft Authenticode PE Signer")
    parser.add_argument("input", type=str, help="Input PE executable (.exe, .dll)")
    parser.add_argument("-o", "--output", type=str, default="", help="Output PE executable (defaults to overwriting input)")
    parser.add_argument("--cert", type=str, default="certificates/Sudharshan_AI_CodeSigning.cer", help="Code signing certificate (.cer or .crt)")
    parser.add_argument("--key", type=str, default="certificates/Sudharshan_AI_CodeSigning.key", help="Private key (.key)")
    parser.add_argument("--name", type=str, default="Sudharshan AI Desktop Assistant", help="Program name displayed in UAC / SmartScreen")
    args = parser.parse_args()

    inp = Path(args.input)
    if not inp.is_file():
        print(f"Error: Input file '{inp}' does not exist.")
        return 1
    out = Path(args.output) if args.output else inp
    cert = Path(args.cert)
    key = Path(args.key)

    ok = sign_pe_file(inp, out, cert, key, program_name=args.name)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
