"""Lector minimo de archivos WingLink ``.tem`` para P2-T.

Solo extrae el encabezado declarado y la tabla de gates. No interpreta ni
corrige la fisica del sondeo. Las unidades se verifican contra la linea de
comentario de ``<DATA>``:

    # Time [ms], Voltage [nV/A], Resistivity [Ohmm]

Si esa linea no aparece, el lector falla en vez de asumir unidades.
"""
from __future__ import annotations

from pathlib import Path
import re

VERSION = "TEM-PARSER-1.0.0"
_EXPECTED_UNITS = ("Time [ms]", "Voltage [nV/A]", "Resistivity [Ohmm]")


def _clean(value: str):
    value = value.split("#", 1)[0].strip()
    if value in ("", "-"):
        return None
    return value


def parse_tem(path: str | Path) -> dict:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if "<DATA>" not in text:
        raise ValueError(f"{path}: falta la seccion <DATA>")

    head, data = text.split("<DATA>", 1)
    if not all(unit in data for unit in _EXPECTED_UNITS):
        raise ValueError(
            f"{path}: no se confirman las unidades esperadas {_EXPECTED_UNITS}"
        )

    header: dict[str, str | None] = {}
    section = None
    for raw in head.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("<") and line.endswith(">"):
            section = line.strip("<>").strip()
            header[f"__section__{section}"] = None
            continue
        parts = line.split(None, 1)
        key = parts[0]
        value = _clean(parts[1]) if len(parts) > 1 else None
        header[key] = value
        if section:
            header[f"{section}.{key}"] = value

    gates = []
    for raw in data.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            t_ms, voltage, rhoa = (float(parts[0]), float(parts[1]), float(parts[2]))
        except ValueError:
            continue
        gates.append(dict(gate=len(gates) + 1, t_ms=t_ms,
                          voltage_nva=voltage, rhoa_ohm_m=rhoa))
    if not gates:
        raise ValueError(f"{path}: no se encontraron gates numericos")

    def number(key: str):
        value = header.get(key)
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return value

    return dict(
        path=str(path),
        file_version=header.get("FILEVERSION"),
        program=header.get("PROGRAM"),
        tem_id=header.get("TEM_ID"),
        project=header.get("PROJECT"),
        coordinate_type=header.get("TYPE"),
        datum=header.get("DATUM"),
        elevation=header.get("ELEVATION"),
        rx_x=number("RXLAT"),
        rx_y=number("RXLONG"),
        tx_x=number("TXLAT"),
        tx_y=number("TXLONG"),
        acquisition_date=header.get("ACQUISITION_DATE"),
        acquisition_time=header.get("ACQUISITION_TIME"),
        receiver=header.get("RECEIVER"),
        transmitter=header.get("TRANSMITTER"),
        configuration=header.get("CONFIGURATION"),
        tx_area_m2=number("TXAREA"),
        rx_area_m2=number("RXAREA"),
        current_a=number("CURRENT"),
        repeat_rate_hz=number("REPTRATE"),
        turnoff_us=number("TURNOFF"),
        antenna_delay_us=number("ANTENNA_DELAY"),
        filter_delay_us=number("FILTER_DELAY"),
        user_delay_us=number("USER_DELAY"),
        n_gates=len(gates),
        t_min_ms=gates[0]["t_ms"],
        t_max_ms=gates[-1]["t_ms"],
        voltage_min_nva=min(g["voltage_nva"] for g in gates),
        voltage_max_nva=max(g["voltage_nva"] for g in gates),
        units=dict(time="ms", voltage="nV/A", resistivity="Ohm*m"),
        gates=gates,
        parser_version=VERSION,
        raw_header=header,
    )


def match_gates(tem: dict, qc_rows: list[dict], time_rel_tol: float = 1e-3):
    """Empareja cada gate ``.tem`` con la fila QC de tiempo mas cercano.

    Devuelve una lista de emparejamientos con la diferencia relativa de tiempo
    y de amplitud. No reordena ni inventa filas: si la diferencia temporal
    excede ``time_rel_tol``, el emparejamiento queda marcado como fallido.
    """
    out = []
    for gate in tem["gates"]:
        t = gate["t_ms"]
        candidates = sorted(qc_rows, key=lambda r: abs(float(r["t_ms"]) - t))
        row = candidates[0]
        t_ref = float(row["t_ms"])
        dt_rel = abs(t_ref - t) / max(abs(t), 1e-12)
        v_ref = float(row["voltage_median_nVA"])
        dv_rel = abs(gate["voltage_nva"] - v_ref) / max(abs(gate["voltage_nva"]), 1e-12)
        out.append(dict(
            gate_tem=gate["gate"],
            t_ms_tem=t,
            voltage_nva_tem=gate["voltage_nva"],
            rhoa_ohm_m_tem=gate["rhoa_ohm_m"],
            gate_reader=int(row["gate"]),
            t_ms_reader=t_ref,
            voltage_nva_reader=v_ref,
            dt_rel=dt_rel,
            dv_rel=dv_rel,
            time_match=bool(dt_rel <= time_rel_tol),
            amplitude_match=bool(dv_rel <= 0.05),
            qc=row["qc"],
            use_contiguous=row["use_contiguous"],
            sigma_effective_nva=float(row["sigma_effective_nVA"]),
            relative_error=float(row["relative_error"]),
            snr_effective=float(row["SNR_effective"]),
        ))
    return out


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) < 2:
        raise SystemExit("uso: python tem_parser.py <archivo.tem>")
    parsed = parse_tem(sys.argv[1])
    parsed.pop("raw_header", None)
    print(json.dumps(parsed, ensure_ascii=False, indent=1))
