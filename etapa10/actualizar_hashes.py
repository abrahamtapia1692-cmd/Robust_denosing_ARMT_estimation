import hashlib
import json
from pathlib import Path

root = Path(".")
cfg_path = root / "etapa10" / "config_p10.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

targets = [
    "etapa7/checkpoints/c_theta_scnet18.pt",
    "etapa7/checkpoints/d_psi_b3_scnet18.pt",
    "etapa7/checkpoints/d_psi_b4_cbam.pt",
    "etapa7/modelos_cbam.py",
    "etapa8/pipeline_armt.py",
    "etapa8/config_p8.json",
    "etapa9/evaluador_ciego.py",
    "etapa9/config_p9.json",
    "banco_sintetico/soporte_S1.json",
    "etapa4/noise_episodes.csv",
]
fh = {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest() for rel in targets}
cfg["frozen_hashes"] = fh
cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(fh, indent=2))
