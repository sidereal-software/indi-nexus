A nightly interop suite that runs against a real `indiserver` and real libindi drivers.
Every other test here reads our own XML with our own parser, which is self-consistent by
construction and so cannot catch a deviation from the spec; these put libindi on the other
side of the wire. It covers libindi's own clients driving our drivers, our client against
all twelve simulators libindi ships, a differential comparison against `indi_getprop`, BLOB
delivery, reconnecting to a real socket, and a browser driving a C++ driver through the
whole stack.

Real traffic captured from those drivers is committed as a fixture and replayed by the fast
suite, so a pull request gets the benefit without libindi installed.
