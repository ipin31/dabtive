from __future__ import annotations
import argparse
import time
from pathlib import Path
import uno
from com.sun.star.beans import PropertyValue


def property_value(name: str, value):
    item = PropertyValue()
    item.Name = name
    item.Value = value
    return item


def connect(port: int):
    local_ctx = uno.getComponentContext()
    resolver = local_ctx.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local_ctx)
    last_error = None
    for _ in range(100):
        try:
            return resolver.resolve(f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext")
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"Tidak dapat tersambung ke LibreOffice: {last_error}")


def encrypt(source: Path, output: Path, password: str, port: int) -> None:
    context = connect(port)
    service_manager = context.ServiceManager
    desktop = service_manager.createInstanceWithContext("com.sun.star.frame.Desktop", context)
    document = desktop.loadComponentFromURL(
        uno.systemPathToFileUrl(str(source.resolve())), "_blank", 0,
        (property_value("Hidden", True), property_value("ReadOnly", False)),
    )
    if document is None:
        raise RuntimeError("LibreOffice gagal membuka master Excel")
    try:
        document.storeAsURL(
            uno.systemPathToFileUrl(str(output.resolve())),
            (
                property_value("FilterName", "Calc MS Excel 2007 XML"),
                property_value("Overwrite", True),
                property_value("Password", password),
            ),
        )
    finally:
        document.close(True)


def verify(source: Path, password: str, port: int) -> None:
    context = connect(port)
    service_manager = context.ServiceManager
    desktop = service_manager.createInstanceWithContext("com.sun.star.frame.Desktop", context)
    document = desktop.loadComponentFromURL(
        uno.systemPathToFileUrl(str(source.resolve())), "_blank", 0,
        (property_value("Hidden", True), property_value("ReadOnly", True), property_value("Password", password)),
    )
    if document is None:
        raise RuntimeError("Password salah atau file terenkripsi tidak dapat dibuka")
    document.close(True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["encrypt", "verify"])
    parser.add_argument("source")
    parser.add_argument("output", nargs="?")
    parser.add_argument("--password", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    if args.mode == "encrypt":
        if not args.output:
            parser.error("output wajib untuk mode encrypt")
        encrypt(Path(args.source), Path(args.output), args.password, args.port)
    else:
        verify(Path(args.source), args.password, args.port)


if __name__ == "__main__":
    main()
