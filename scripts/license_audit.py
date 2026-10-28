"""Write THIRD_PARTY_LICENSES.txt and fail on GPL-3.0-incompatible packages."""

from foamstudio.core.licenses import main

if __name__ == "__main__":
    raise SystemExit(main())
