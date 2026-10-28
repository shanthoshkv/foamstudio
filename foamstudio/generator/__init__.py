"""Bridge to openfoam_case_generator.html. Do not reimplement the dictionary writer here.

Chromium reads the variables below when Qt WebEngine is first imported. Setting them
here covers ``bridge`` without affecting the Node host in ``headless``.
"""

import os

os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")
