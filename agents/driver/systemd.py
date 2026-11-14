"""systemd birim üretimi — instance/rol başına, sabit yol yok."""

from __future__ import annotations

from pathlib import Path


def birim_adi(instance: str, rol: str) -> str:
    return f"agents@{instance}-{rol}.service"


def servis_metni(instance: str, rol: str, exec_start: str, state_dir: Path,
                 env: dict[str, str] | None = None) -> str:
    satirlar = [
        "[Unit]",
        f"Description=agents {instance} {rol}",
        "After=network-online.target",
        f"OnFailure=agents-notify@{instance}.service",
        "",
        "[Service]",
        "Type=simple",
        f"WorkingDirectory={Path(state_dir)}",
        f"ExecStart={exec_start}",
        "Restart=always",
        "RestartSec=5",
        "StartLimitIntervalSec=0",
        "KillMode=control-group",
        "NoNewPrivileges=true",
    ]
    for k, v in (env or {}).items():
        satirlar.append(f"Environment={k}={v}")
    satirlar += ["", "[Install]", "WantedBy=default.target", ""]
    return "\n".join(satirlar)


def notify_metni() -> str:
    return chr(10).join([
        "[Unit]", "Description=agents failure notify", "",
        "[Service]", "Type=oneshot",
        "ExecStart=/bin/echo agents %i failed", ""])


def birim_yolu(instance: str, rol: str, systemd_dir: Path) -> Path:
    return Path(systemd_dir) / birim_adi(instance, rol)
