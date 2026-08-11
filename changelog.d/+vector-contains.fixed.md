`"RA" in vector` now answers truthfully. `Vector` defined `__getitem__` without
`__contains__`, so Python fell back to indexing 0, 1, 2 against a name lookup and returned
`False` for an element that was present, without raising. The interop suite found it by
writing the obvious thing.
