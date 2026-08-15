# Drivers for the container

`compose.yaml` mounts this directory read-only at `/drivers`, and everything in it is
launched under `indiserver` alongside whatever `INDI_DRIVERS` names. Drop a driver in
and run `docker compose up`.

Two kinds of file work here:

- a `.py` driver written against the INDINexus SDK, which needs no executable bit -
  the container wraps it in a shim that runs it under the interpreter the package is
  installed into;
- any other executable, which is run as-is. That covers a compiled C++ driver, or a
  Python driver for some other framework with its own shebang and dependencies.

Anything else is skipped with a line in the log, so a note like this one does not get
handed to `indiserver`.

Nothing here is tracked by git except this file.
