Name:           sudharshan-ai
Version:        1.0.0
Release:        1%{?dist}
Summary:        Sudharshan AI — Local-First Desktop AI Operating Layer
License:        MIT
URL:            https://github.com/rkrworks/Sudharshan-AI
BuildArch:      noarch
Requires:       python3 >= 3.11, gtk4, libadwaita, python3-gobject

%description
Sudharshan AI is a local-first, fail-closed desktop AI assistant powered by an adaptive Qwen 3.5 multi-model local engine via Ollama.

%install
mkdir -p %{buildroot}%{_datadir}/sudharshan-ai
cp -r bajrang_core.py fedora.py sudharshan_cli.py design_tokens.json sudharshan %{buildroot}%{_datadir}/sudharshan-ai/
mkdir -p %{buildroot}%{_bindir}
cat << 'EOF' > %{buildroot}%{_bindir}/sudharshan
#!/usr/bin/env bash
exec python3 %{_datadir}/sudharshan-ai/sudharshan_cli.py "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/sudharshan

%files
%{_bindir}/sudharshan
%{_datadir}/sudharshan-ai/
