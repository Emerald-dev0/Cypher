# Contributing to CYPHER

Thanks for helping improve CYPHER. The project contains an Android Flutter app, a Windows Flutter companion, and the Python backend used by the companion.

## Before opening a pull request

1. Run `flutter pub get`, `flutter analyze`, and `flutter test` in each Flutter app you change.
2. Run `python -m compileall -q core *.py` from `pc_app_flutter/backend` when changing the backend.
3. Keep changes focused and explain user-visible behavior in the pull request description.
4. Do not commit generated build output, credentials, pairing tokens, or personal device information.

## Pull requests

Please include a short summary, the verification commands you ran, and screenshots or recordings for meaningful UI changes.
