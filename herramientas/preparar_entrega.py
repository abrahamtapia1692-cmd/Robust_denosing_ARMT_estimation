"""Genera Word y la matriz de seguimiento a partir del plan revisable en Markdown."""
import csv
import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

ROOT = Path(__file__).resolve().parents[1]


def inline(paragraph, text):
    pattern = r"(\*\*.*?\*\*|\[.*?\]\(.*?\))"
    for part in re.split(pattern, text):
        if part.startswith("**") and part.endswith("**"):
            paragraph.add_run(part[2:-2]).bold = True
        elif re.fullmatch(r"\[.*?\]\(.*?\)", part):
            label, url = re.match(r"\[(.*?)\]\((.*?)\)", part).groups()
            rel = paragraph.part.relate_to(
                url,
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                is_external=True,
            )
            link = OxmlElement("w:hyperlink")
            link.set(qn("r:id"), rel)
            run = OxmlElement("w:r")
            prop = OxmlElement("w:rPr")
            color = OxmlElement("w:color")
            color.set(qn("w:val"), "176B87")
            prop.append(color)
            run.append(prop)
            txt = OxmlElement("w:t")
            txt.text = label
            run.append(txt)
            link.append(run)
            paragraph._p.append(link)
        else:
            paragraph.add_run(part)


def make_docx(source_name, output_name):
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(1.9)
    section.left_margin = section.right_margin = Cm(1.8)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.08
    for name in ["Heading 1", "Heading 2", "Heading 3"]:
        doc.styles[name].font.name = "Calibri"
        doc.styles[name].font.color.rgb = RGBColor.from_string("124559")
        doc.styles[name].paragraph_format.keep_with_next = True
    doc.styles["Title"].font.size = Pt(25)
    doc.styles["Title"].font.color.rgb = RGBColor.from_string("124559")
    header = section.header.paragraphs[0]
    header.text = "ARMT  |  RUTA DE IMPLEMENTACIÓN Y VALIDACIÓN"
    header.style = doc.styles["Caption"]
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run("28 octubre 2026 · v1.3   |   ")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    lines = (ROOT / source_name).read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            p = doc.add_paragraph()
            run = p.add_run("\n".join(block))
            run.font.name = "Consolas"
            run.font.size = Pt(8)
            shade = OxmlElement("w:shd")
            shade.set(qn("w:fill"), "EEF4F6")
            p._p.get_or_add_pPr().append(shade)
            p.paragraph_format.keep_together = True
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"[:\- ]+", c) for c in cells):
                    rows.append(cells)
                i += 1
            table = doc.add_table(rows=1, cols=len(rows[0]))
            table.style = "Light Shading Accent 1"
            for index, values in enumerate(rows):
                assert len(values) == len(rows[0]), (source_name, values)
                row = table.rows[0] if index == 0 else table.add_row()
                trpr = row._tr.get_or_add_trPr()
                trpr.append(OxmlElement("w:cantSplit"))
                if index == 0:
                    trpr.append(OxmlElement("w:tblHeader"))
                for cell, value in zip(row.cells, values):
                    p = cell.paragraphs[0]
                    inline(p, value)
                    p.paragraph_format.space_after = Pt(4)
                    p.paragraph_format.space_before = Pt(3)
                    for run in p.runs:
                        run.font.size = Pt(8.5)
                        if index == 0:
                            run.bold = True
            doc.add_paragraph()
            continue
        elif line.startswith("# "):
            doc.add_paragraph(line[2:], "Title")
        elif line.startswith("### "):
            doc.add_heading(line[4:], level=2)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=1)
        elif re.match(r"^\d+\. ", line):
            p = doc.add_paragraph(style="List Number")
            inline(p, re.sub(r"^\d+\. ", "", line))
        elif line.startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            inline(p, line[2:])
        else:
            p = doc.add_paragraph()
            inline(p, line.rstrip())
        i += 1
    props = doc.core_properties
    props.title = lines[0].lstrip("# ")
    props.subject = "MT/AMT con soporte TEM, episodios de ruido y aprendizaje supervisado"
    props.author = "Documento de trabajo técnico"
    props.version = "1.3"
    target = ROOT / output_name
    doc.save(target)
    reopened = Document(target)
    expected_tables = sum(bool(re.fullmatch(r"\|[-:\s|]+\|", line)) for line in lines)
    assert len(reopened.tables) == expected_tables, (len(reopened.tables), expected_tables)
    headings = [line.lstrip("# ") for line in lines if line.startswith(("# ", "## ", "### "))]
    paragraphs = {p.text for p in reopened.paragraphs}
    assert all(heading in paragraphs for heading in headings)
    print(f"{output_name}: {len(reopened.paragraphs)} párrafos, {len(reopened.tables)} tablas")


def make_matrix():
    rows = [
        ("P0", "0", "Inventario y contrato MT/AMT", "Ninguna", "D0/D1, gates TEM, schema, particiones y protocolo", "Cero grupos compartidos; D2/D3 fuera de la red", "Datos / coordinación"),
        ("P1", "1", "Calibración y QC", "P0", "Prueba instrumental, soporte CLB y máscaras", "Meta inicial ideal: amplitud ≤1%, fase ≤1°; ajustar con medición real", "Instrumentación / física"),
        ("P2", "2", "Conjunto de modelos TEM", "P0", "Gates válidos, forwards independientes, escenarios y resolución", "Meta numérica Z ≤1% y fase ≤0.5° frente a referente; no certifica soporte TEM", "Física EM / inversión"),
        ("P2-T", "2.8-2.11", "Soporte TEM–MT/AMT por sondeo", "P1;P2", "Jacobianos, modelos equivalentes, envolventes y tem_amt_support.csv", "Tolerancias predictivas preregistradas; parcial/vacío permitido; F_red_validada por subbanda; G0 no extrapola etiquetas", "Física EM / incertidumbre"),
        ("P3", "3", "Síntesis de subbanda", "P1;P2;P2-T;referencia inicial", "Cierre E=ZH, Hz=TH, filtro común y guardas", "Residuo <1e-8 donde aplica; sin blancos TEM fuera de soporte", "Modelado / señales"),
        ("P4", "4", "Banco de ruido BSS", "P1;P3", "Reconstrucción, fuga, fuentes y matrices de mezcla", "Metas iniciales: error RMS <1%; energía útil extraída <5% en inyecciones", "BSS / señales"),
        ("P4-N", "4.5-4.9", "Admisión de episodios de ruido", "P4", "Forma, tiempos, huella multicanal, evidencia y estabilidad", "Coherencia sola no admite ruido; no exigir Sx/Sy ni Zopt; ρ_comp compatible con TEM es evidencia asimétrica", "BSS / evidencia de campo"),
        ("P5", "5", "Dataset independiente por subbanda", "P2-T;P3;P4", "Pares, máscaras TEM, incertidumbre de etiquetas y particiones", "Cero fuga de grupos y cero etiquetas TEM fuera de soporte; familia de ruido independiente y pareo de potencia", "Datos / aprendizaje"),
        ("P5-L", "5", "Etiquetas y pares admisibles", "P2-T;P4-N;P5", "Manifiestos D_id/D_sep/D_real y auditoría de blancos", "Cero blancos inventados para campo sin referencia; exactos/aproximados explícitos", "Datos / validación"),
        ("P6", "6", "Estimador e incertidumbre", "P1;P3 para cierre completo", "Sesgo, rango, ruido en H, Monte Carlo y referencia", "Recuperación identificable y cobertura calibrada por escenario; sin bracket como cota general", "Estimación / estadística"),
        ("P7", "7", "Detector y separador CBAM MT/AMT", "P5-L;P6", "Comparadores y controles por subbanda D0/D1", "Mejora de transferencia y conservación limpia; sin adaptación RMT; superar B7/B8", "Aprendizaje / validación"),
        ("P7-I", "7", "Validación del detector", "P5-L;P7 desarrollo", "FPR, sensibilidad, PR-AUC y calibración tras agregación temporal", "Metas piloto FPR tiempo limpio ≤1%; sensibilidad ≥90% en episodios detectables; B7 solo-potencia", "Clasificación / validación"),
        ("P7-S", "7", "Separación y conexión detector–separador", "P5-L;P6;P7-I", "Máscara ideal/predicha; blancos exactos/aproximados; preservación Z", "Metas de Z/fase del plan y no inferioridad limpia con máscara real; B8/B10 y prueba de sobresupresión a −20 dB", "Separación / física"),
        ("P8", "8", "Inferencia MT/AMT con soporte parcial", "P1;P2-T;P6;P7-I;P7-S", "F_aplicacion, máscara temporal, proyección, guardas y exclusiones", "Cero intervención fuera de soporte o en D2/D3; soporte vacío omite red; F_red_validada congelada; G3 antes de P9", "Integración / señales"),
        ("P9", "9", "Evaluación ciega de soporte y recuperación", "P2-T;P5 congelado;P6;P7;P8", "Validez de máscara TEM y rendimiento por subbanda/sitio", "Métricas preregistradas; falsa recuperación objetivo ≤5%; denominadores explícitos; modelo jerárquico y multiplicidad; G4", "Validación independiente"),
        ("P10", "10", "Liberación por dominio", "P9", "Reporte reproducible, hashes, covarianzas y regreso a referencia", "Reproducción por otra persona y dominio de uso documentado; hashes de W_b, escalas, umbrales y F_aplicacion", "Integración / coordinación"),
    ]
    headers = ["puerta", "etapa", "objetivo", "dependencias", "evidencia_requerida", "criterio_inicial", "responsable_funcional", "estado", "dominio", "fecha_revision", "ruta_evidencia", "observaciones"]
    observaciones = {
        "P2-T": "v1.3: F_red_validada por subbanda (L, fs_eff, Δf, f_min, N_c); G0 admite soporte vacío sin ampliar la máscara",
        "P5": "v1.3: reservar familia de ruido de mecanismo distinto (B9); parear potencia de negativos limpios; detectabilidad declarada antes de la prueba",
        "P7-I": "v1.3: comparador solo-potencia B7 y métricas estratificadas por SNR; oráculo ≥90% sensibilidad con ≤1% FPR",
        "P7-S": "v1.3: B8 Wiener con S_nn verdadera/estimada, B10 oráculo de ruido; no imponer dos naturales más dos ruidos",
        "P8": "v1.3: F_aplicacion incluye F_red_validada; G3 exige ≥3 sitios independientes y subconjunto detectable ≥30%",
        "P9": "v1.3: endpoint preregistrado, modelo jerárquico, intervalos cluster-robustos, multiplicidad y sharpness; G4 no libera si falla no inferioridad",
        "P10": "v1.3: congelar hashes de W_b, escalas, umbrales, agregación y F_aplicacion antes de abrir la prueba ciega",
    }
    default_obs = "v1.3: episodios, etiquetas y detector/separador; metas propuestas, no certificadas"
    with (ROOT / "MATRIZ_VALIDACION_ARMT.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([*row, "Pendiente de implementación/validación", "MT/AMT D0/D1; solo soporte habilitado", "", "", observaciones.get(row[0], default_obs)])
    print(f"Matriz: {len(rows)} controles")


def make_label_matrix():
    rows = [
        ("S0", "Sintético limpio", "s", "0", "s", "exact_synthetic", "Sí", "Sí: identidad", "Modelo base y fuente", "Sin contaminación objetivo; piso instrumental declarado"),
        ("S1", "Sintético contaminado", "s+n conocido", "Actividad inyectada; detectabilidad declarada", "s", "exact_synthetic", "Sí", "Sí", "Modelo, fuente y ruido padre", "P2-T en etiquetas TEM; no exigir detección bajo el piso"),
        ("S2", "Sintético con ruido extraído", "s+N admitido", "Actividad de inyección conocida", "s", "exact_synthetic", "Sí", "Sí: semisintético", "Modelo y episodio/plantilla de campo", "Blanco exacto de construcción; pureza física de N tiene incertidumbre"),
        ("F0", "Campo de bajo ruido aceptado", "r", "0 aproximado con evidencia", "r", "approx_field", "Sí: confianza explícita", "Identidad aproximada", "Registro, sitio y campaña", "r conserva residual desconocido; no afirmar verdad limpia absoluta"),
        ("F1", "Campo F0 con ruido añadido", "r+n conocido", "Actividad añadida y estado del fondo", "r", "approx_field", "Sí: confianza explícita", "Sí: retirar ruido añadido", "Registro base y episodio/plantilla", "No certifica eliminación del ruido residual presente en r"),
        ("F2", "Campo original contaminado", "x_real", "1 solo en episodios anotados; resto ignore", "", "unavailable", "Solo anotados", "No: falta blanco", "Registro, sitio y campaña", "Extracción/evaluación permitidas; no inventar blanco TEM temporal"),
        ("U", "Campo ambiguo", "x_real", "ignore", "", "unavailable", "No supervisado", "No", "Registro, sitio y campaña", "Inspección o investigación separada; no pseudo-verdad BSS automática"),
        ("N", "Solo ruido diseñado", "n", "Actividad conocida y ausencia de señal", "0 diseñado", "exact_control", "Control separado", "Solo control de no alucinación", "Episodio/plantilla", "No producir impedancia válida ni mezclar su métrica con recuperación normal"),
    ]
    headers = ["familia", "origen", "entrada", "etiqueta_identificacion", "blanco_separacion", "tipo_blanco", "uso_D_id", "uso_D_sep", "grupo_a_preservar", "restriccion"]
    with (ROOT / "MATRIZ_ETIQUETAS_AMT.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"Etiquetas: {len(rows)} familias")


if __name__ == "__main__":
    make_docx("PLAN_IMPLEMENTACION_ARMT.md", "PLAN_IMPLEMENTACION_ARMT_v1_3.docx")
    make_docx("DISENO_RUIDOS_DATASET_AMT.md", "DISENO_RUIDOS_DATASET_AMT_v1_3.docx")
    make_matrix()
    make_label_matrix()
