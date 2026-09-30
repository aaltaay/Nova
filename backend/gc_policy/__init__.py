"""The backend process's garbage-collector policy (#619): freeze the long-lived heap once startup settles.

A full (gen-2) collection stops every thread while it walks every tracked object. Minutes after a
start about three quarters of them are code, classes and module state that live as long as the
process (the 2026-09-29 census: 732,138 objects, most of them functions, dicts, tuples, cells and
types). ``gc.freeze()`` moves them out of every later collection; what the process creates
afterwards is collected as before.
"""
