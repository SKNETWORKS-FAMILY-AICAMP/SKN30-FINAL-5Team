from pathlib import Path

# This workspace-local entry point adapts the bundled renderer's Windows
# LibreOffice profile URI, then runs the original implementation unchanged.
import runpy
import sys


original = Path(
    r"C:\Users\playdata2\.codex\plugins\cache\openai-primary-runtime\documents"
    r"\26.521.10419\skills\documents\render_docx.py"
)
source = original.read_text(encoding="utf-8")
source = source.replace(
    '"-env:UserInstallation=file://" + user_profile',
    '"-env:UserInstallation=" + Path(user_profile).resolve().as_uri()',
)
source = "from pathlib import Path\n" + source
code = compile(source, str(original), "exec")
namespace = {"__name__": "__main__", "__file__": str(original)}
exec(code, namespace)
