from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _cell_ref(column: int, row: int) -> str:
    letters = ""
    value = column
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def _inline_cell(column: int, row: int, value: object, style: int = 4) -> str:
    text = "" if value is None else str(value)
    preserve = ' xml:space="preserve"' if text != text.strip() else ""
    return (
        f'<c r="{_cell_ref(column, row)}" t="inlineStr" s="{style}">'
        f'<is><t{preserve}>{escape(text)}</t></is></c>'
    )


def _number_cell(column: int, row: int, value: int | float, style: int = 6) -> str:
    return f'<c r="{_cell_ref(column, row)}" s="{style}"><v>{value}</v></c>'


def _row(row_number: int, cells: list[str], *, height: int | None = None) -> str:
    attrs = f' r="{row_number}"'
    if height:
        attrs += f' ht="{height}" customHeight="1"'
    return f"<row{attrs}>{''.join(cells)}</row>"


def build_leads_xlsx(rows: list[dict[str, object]], generated_at: str) -> bytes:
    """Create a styled, formula-safe XLSX export using only the Python standard library."""
    headers = [
        "Tanggal Request",
        "Nama",
        "Nomor WhatsApp",
        "Email",
        "Jenis Bisnis",
        "File / Campaign",
        "License ID",
        "Status Pembayaran",
        "Nominal",
        "Status File",
        "Jumlah Download",
        "Link Expired",
    ]

    sheet_rows: list[str] = []
    sheet_rows.append(_row(1, [_inline_cell(1, 1, "DABTIVE LEADS DATABASE", 1)], height=32))
    sheet_rows.append(_row(2, [_inline_cell(1, 2, f"Generated: {generated_at} · Total leads: {len(rows):,}", 2)], height=22))
    sheet_rows.append(_row(3, [], height=8))
    sheet_rows.append(_row(4, [_inline_cell(index, 4, header, 3) for index, header in enumerate(headers, 1)], height=26))

    for offset, item in enumerate(rows, 5):
        status = str(item.get("status") or "").upper()
        payment_status = str(item.get("payment_status") or "").upper()
        status_style = 7 if status == "READY" else 8 if status == "FAILED" else 9
        payment_style = 7 if payment_status in {"PAID", "NOT_REQUIRED"} else 9
        cells = [
            _inline_cell(1, offset, item.get("created_at")),
            _inline_cell(2, offset, item.get("name")),
            _inline_cell(3, offset, item.get("whatsapp")),
            _inline_cell(4, offset, item.get("email")),
            _inline_cell(5, offset, item.get("business_type")),
            _inline_cell(6, offset, item.get("campaign")),
            _inline_cell(7, offset, item.get("license_id")),
            _inline_cell(8, offset, payment_status, payment_style),
            _number_cell(9, offset, int(item.get("payment_amount") or 0)),
            _inline_cell(10, offset, status, status_style),
            _number_cell(11, offset, int(item.get("downloads") or 0)),
            _inline_cell(12, offset, item.get("expires_at")),
        ]
        sheet_rows.append(_row(offset, cells, height=22))

    last_row = max(4, len(rows) + 4)
    worksheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>
  <dimension ref="A1:L{last_row}"/>
  <sheetViews><sheetView workbookViewId="0"><pane ySplit="4" topLeftCell="A5" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <sheetFormatPr defaultRowHeight="18"/>
  <cols>
    <col min="1" max="1" width="21" customWidth="1"/>
    <col min="2" max="2" width="24" customWidth="1"/>
    <col min="3" max="3" width="19" customWidth="1"/>
    <col min="4" max="4" width="31" customWidth="1"/>
    <col min="5" max="5" width="24" customWidth="1"/>
    <col min="6" max="6" width="29" customWidth="1"/>
    <col min="7" max="7" width="23" customWidth="1"/>
    <col min="8" max="8" width="18" customWidth="1"/>
    <col min="9" max="9" width="16" customWidth="1"/>
    <col min="10" max="10" width="16" customWidth="1"/>
    <col min="11" max="11" width="17" customWidth="1"/>
    <col min="12" max="12" width="21" customWidth="1"/>
  </cols>
  <sheetData>{''.join(sheet_rows)}</sheetData>
  <mergeCells count="2"><mergeCell ref="A1:L1"/><mergeCell ref="A2:L2"/></mergeCells>
  <autoFilter ref="A4:L{last_row}"/>
  <pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
  <pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>
</worksheet>'''

    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="5">
    <font><sz val="10"/><name val="Aptos"/><family val="2"/></font>
    <font><b/><sz val="18"/><color rgb="FFFFFFFF"/><name val="Aptos Display"/></font>
    <font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font>
    <font><sz val="10"/><color rgb="FF111111"/><name val="Aptos"/></font>
    <font><b/><sz val="9"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font>
  </fonts>
  <fills count="7">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF111111"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE1162B"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE8F8EF"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFE7EA"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFF3CF"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border><left style="thin"><color rgb="FFE1E1E5"/></left><right style="thin"><color rgb="FFE1E1E5"/></right><top style="thin"><color rgb="FFE1E1E5"/></top><bottom style="thin"><color rgb="FFE1E1E5"/></bottom><diagonal/></border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="10">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="3" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="3" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="5" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="6" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
  <dxfs count="0"/>
  <tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>
</styleSheet>'''

    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <bookViews><workbookView xWindow="0" yWindow="0" windowWidth="24000" windowHeight="14000"/></bookViews>
  <sheets><sheet name="Leads" sheetId="1" r:id="rId1"/></sheets>
  <calcPr calcId="191029"/>
</workbook>'''

    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''

    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''

    workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    core = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Dabtive Leads Database</dc:title><dc:creator>Dabtive Excel Access</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>'''
    app = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Dabtive Excel Access</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>
  <HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant><vt:variant><vt:i4>1</vt:i4></vt:variant></vt:vector></HeadingPairs>
  <TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr>Leads</vt:lpstr></vt:vector></TitlesOfParts>
</Properties>'''

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", styles)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return buffer.getvalue()
