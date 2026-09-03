from __future__ import absolute_import, division, print_function
from libtbx.test_utils import Exception_expected
import sys

def run(args):
  assert len(args) == 0
  try:
    import numpy as np
  except ImportError:
    print("numpy not available, skipping")
    print("OK")
    return
  from scitbx.array_family import flex
  if flex.int().as_numpy_array(optional=True) is None:
    # numpy was not available when the extension was built, so the scalar
    # converters were not compiled in either
    print("numpy support not compiled in, skipping")
    print("OK")
    return

  exercise_original_reproducer(np, flex)
  exercise_element_setitem(np, flex)
  exercise_element_iadd(np, flex)
  exercise_array_iadd(np, flex)
  exercise_construction_from_numpy_scalars(np, flex)
  exercise_value_preservation(np, flex)
  exercise_integer_overflow(np, flex)
  exercise_integer_arithmetic_semantics(np, flex)
  exercise_timedelta_is_left_to_numpy(np, flex)
  exercise_numpy_bool(np, flex)
  exercise_wider_integer_targets(np, flex)
  exercise_unsigned_overflow_parity(np, flex)
  exercise_complex_target(np, flex)
  exercise_reversed_operand_caveat(np, flex)
  print("OK")

def assert_overflow(f):
  try:
    f()
  except OverflowError:
    pass
  else:
    raise Exception_expected

def assert_type_error(f):
  try:
    f()
  except TypeError:
    pass
  else:
    raise Exception_expected

def accepts(a, value):
  try:
    a[0] = value
  except OverflowError:
    return False
  return True

def exercise_original_reproducer(np, flex):
  """Reproducer from https://github.com/cctbx/cctbx_project/issues/1084"""
  arr = flex.double(10)
  arr[0] += np.array([1,2,3], dtype=np.float32)[0]
  assert arr[0] == 1.0

def exercise_element_setitem(np, flex):
  """Test arr[i] = numpy_scalar for various type combinations.

  Exact dtype matches (np.float64 -> flex.double, np.float32 -> flex.float,
  np.int32 -> flex.int, np.int64 -> flex.long) already convert through
  Boost.Python's own converters; every other combination below needs the
  converters in numpy_bridge.cpp."""
  # float scalars -> flex.double
  a = flex.double(1)
  for val in [np.float32(3.5), np.float64(3.5), np.float16(3.5)]:
    a[0] = val
    assert a[0] == 3.5, (a[0], type(val))
  # integer scalars -> flex.double (implicit widening)
  for val in [np.int32(7), np.int64(7), np.uint32(7), np.int8(7)]:
    a[0] = val
    assert a[0] == 7.0, (a[0], type(val))
  # float and integer scalars -> flex.float
  b = flex.float(1)
  for val in [np.float32(2.5), np.float64(2.5)]:
    b[0] = val
    assert abs(b[0] - 2.5) < 1e-6, (b[0], type(val))
  b[0] = np.int64(3)
  assert b[0] == 3.0
  # integer scalars -> flex.int
  c = flex.int(1)
  for val in [np.int32(42), np.int64(42), np.uint8(42)]:
    c[0] = val
    assert c[0] == 42, (c[0], type(val))
  # integer scalars -> flex.long
  d = flex.long(1)
  for val in [np.int32(42), np.int64(42)]:
    d[0] = val
    assert d[0] == 42, (d[0], type(val))
  # numpy integers as indices, including negative ones
  e = flex.double([5.0, 6.0])
  assert e[np.int32(1)] == 6.0
  assert e[np.int64(-1)] == e[-1] == 6.0

def exercise_element_iadd(np, flex):
  """Test arr[i] += numpy_scalar for various type combinations."""
  a = flex.double([10.0])
  a[0] += np.float32(2.5)
  assert a[0] == 12.5
  a[0] += np.float64(1.0)
  assert a[0] == 13.5
  a[0] += np.int32(1)
  assert a[0] == 14.5
  a[0] += np.int64(1)
  assert a[0] == 15.5

  b = flex.int([10])
  b[0] += np.int32(5)
  assert b[0] == 15
  b[0] += np.int64(3)
  assert b[0] == 18

def exercise_array_iadd(np, flex):
  """Test arr += numpy_scalar (whole-array operations)."""
  a = flex.double([1.0, 2.0, 3.0])
  a += np.float32(10.0)
  assert list(a) == [11.0, 12.0, 13.0]
  a += np.float64(1.0)
  assert list(a) == [12.0, 13.0, 14.0]
  a += np.int32(1)
  assert list(a) == [13.0, 14.0, 15.0]

  b = flex.int([1, 2, 3])
  b += np.int32(10)
  assert list(b) == [11, 12, 13]
  b += np.int64(1)
  assert list(b) == [12, 13, 14]

def exercise_construction_from_numpy_scalars(np, flex):
  """Test constructing flex arrays from lists containing numpy scalars."""
  a = flex.double([np.float32(1.0), np.float64(2.0), np.float32(3.0)])
  assert list(a) == [1.0, 2.0, 3.0]
  b = flex.int([np.int32(1), np.int32(2), np.int32(3)])
  assert list(b) == [1, 2, 3]
  c = flex.int([np.int64(1), np.int64(2)])
  assert list(c) == [1, 2]
  d = flex.double([np.float16(1.5), np.int8(2)])
  assert list(d) == [1.5, 2.0]

def exercise_value_preservation(np, flex):
  """Test that values are preserved accurately through conversion."""
  # float32 has ~7 decimal digits of precision
  a = flex.double(1)
  a[0] = np.float32(1.23456789)
  # float32 truncates, so check against float32 precision
  assert abs(a[0] - float(np.float32(1.23456789))) < 1e-10

  # float64 should be exact for representable values
  a[0] = np.float64(1.234567890123456)
  assert a[0] == 1.234567890123456

  # Large integers
  b = flex.int(1)
  b[0] = np.int32(2147483647)  # INT32_MAX
  assert b[0] == 2147483647

def exercise_integer_overflow(np, flex):
  """Out-of-range numpy integers raise OverflowError and leave the array
  untouched; in-range values of any numpy width are accepted."""
  c = flex.int([0])
  for ok in [np.int64(2**31 - 1), np.int64(-2**31), np.uint64(5),
             np.uint8(255)]:
    c[0] = ok
    assert c[0] == int(ok), (c[0], ok)
  c[0] = 7
  for bad in [np.int64(2**31), np.int64(-2**31 - 1),
              np.uint64(2**32 - 1), np.uint64(2**63)]:
    assert_overflow(lambda: c.__setitem__(0, bad))
    assert c[0] == 7, (c[0], bad)
  # flex.long is 32 bits wide on Windows and 64 bits elsewhere: a numpy
  # integer is accepted exactly when the same Python int is accepted.
  l = flex.long([0])
  for v in [2**40, 2**62]:
    assert accepts(l, v) == accepts(l, np.int64(v)), v
  assert_overflow(lambda: l.__setitem__(0, np.uint64(2**63)))

def exercise_integer_arithmetic_semantics(np, flex):
  """flex integer arrays combined with a numpy integer use the C++ integer
  operators (truncating division, C-style modulo), exactly as with a Python
  int operand, instead of falling through to NumPy's float division."""
  for a, s in [(flex.int([3, -7]), np.int64(2)),
               (flex.long([3, -7]), np.int32(2)),
               (flex.size_t([3, 7]), np.int64(2))]:
    q = a / s
    assert type(q) is type(a), (type(q), type(a))
    assert list(q) == list(a / int(s)), (list(q), list(a / int(s)))
    r = a % s
    assert type(r) is type(a), (type(r), type(a))
    assert list(r) == list(a % int(s)), (list(r), list(a % int(s)))
  assert list(flex.int([3, -7]) / np.int64(2)) == [1, -3]
  assert list(flex.int([-7]) % np.int64(3)) == [-1]
  # overflow wraps as it does in C++ (and with a Python int operand)
  assert list(flex.int8([2]) * np.int64(100)) \
      == list(flex.int8([2]) * 100) == [-56]
  assert list(flex.size_t([1]) - np.int64(2)) == list(flex.size_t([1]) - 2)
  assert_overflow(lambda: flex.size_t([1]) == np.int64(-1))

def exercise_timedelta_is_left_to_numpy(np, flex):
  """np.timedelta64 subclasses np.signedinteger but is a duration, not a
  number: it must fall through to NumPy's reflected operators as it did
  before the converters existed."""
  d = flex.double([1.0])
  r = d * np.timedelta64(5, 's')
  assert isinstance(r, np.ndarray) and r.dtype.kind == 'm', r
  r = d == np.timedelta64(5, 's')
  assert isinstance(r, np.ndarray) and list(r) == [False], r
  r = flex.int([1]) + np.timedelta64(5)
  assert isinstance(r, np.ndarray) and r.dtype.kind == 'm', r

def exercise_numpy_bool(np, flex):
  """np.bool_ converts to the floating-point and complex types, as Python
  True/False does, but deliberately not to the integer types: a NumPy
  boolean mask handed to a method taking an index sequence would otherwise
  be consumed as the index set {0, 1} instead of raising."""
  a = flex.double(1)
  a[0] = np.True_
  assert a[0] == 1.0
  c = flex.double(2)
  c.fill(np.True_)
  assert list(c) == [1.0, 1.0]
  b = flex.bool(1)
  b[0] = np.True_
  assert b[0]
  for mk in [flex.int, flex.size_t]:
    assert_type_error(lambda: mk(1).__setitem__(0, np.True_))
  assert isinstance(flex.int([1, 2]) * np.True_, np.ndarray)
  d = flex.double([10.0, 20.0, 30.0])
  assert_type_error(lambda: d.select(np.array([True, False, True])))
  # the other exception to "behaves like the Python scalar": Python ints
  # coerce to bool, NumPy integers do not
  b[0] = 0
  assert not b[0]
  assert_type_error(lambda: b.__setitem__(0, np.int64(1)))

def exercise_wider_integer_targets(np, flex):
  """Every flex integer element type, and every size or index parameter,
  accepts numpy integers of any dtype."""
  for mk in [flex.size_t, flex.uint8, flex.uint16, flex.uint32,
             flex.int8, flex.int16]:
    a = mk(1)
    for val in [np.int64(3), np.int32(3), np.uint64(3), np.uint8(3)]:
      a[0] = val
      assert a[0] == 3, (mk, val)
  a = flex.int8(1)
  a[0] = np.int64(-3)
  assert a[0] == -3
  a = flex.int16(1)
  a[0] = np.int32(-300)
  assert a[0] == -300
  # std::size_t and int64_t parameters
  assert flex.double(np.int64(3)).size() == 3
  a = flex.double(1)
  a.resize(np.int64(4))
  assert a.size() == 4
  a.reserve(np.int32(8))
  assert flex.random_double(np.int64(3)).size() == 3
  assert list(flex.size_t_range(np.int64(3))) == [0, 1, 2]
  sel = flex.size_t([np.int64(0), np.int64(1)])
  assert list(sel) == [0, 1]
  picked = flex.double([5.0, 6.0, 7.0]).select(flex.size_t([np.int64(2)]))
  assert list(picked) == [7.0]
  # an integer ndarray reaches the std::set<unsigned> overload, like a
  # Python list does: sorted unique indices, not the flex.size_t gather
  d = flex.double([10.0, 20.0, 30.0])
  assert list(d.select(np.array([2, 0, 2]))) \
      == list(d.select([2, 0, 2])) == [10.0, 30.0]

def exercise_unsigned_overflow_parity(np, flex):
  """Range violations raise OverflowError, as they do for a Python int
  (Boost.Python commits to an overload before checking the range)."""
  s = flex.size_t([1])
  assert_overflow(lambda: s.__setitem__(0, np.int64(-1)))
  assert s[0] == 1
  u = flex.uint8([1])
  assert_overflow(lambda: u.__setitem__(0, np.int64(300)))
  assert_overflow(lambda: u.__setitem__(0, np.int32(-1)))
  assert u[0] == 1
  i = flex.int8([1])
  assert_overflow(lambda: i.__setitem__(0, np.int64(200)))
  assert_overflow(lambda: flex.double(np.int64(-1)))
  # np.uint64 beyond the long long range still reaches size_t (through
  # Boost.Python's exact-dtype converter), exactly when the Python int does
  for v in [2**63, 2**64 - 1]:
    assert accepts(s, v) == accepts(s, np.uint64(v)), v
    if accepts(s, v):
      s[0] = np.uint64(v)
      assert s[0] == v

def exercise_complex_target(np, flex):
  """Real and complex numpy scalars convert to std::complex<double>, as
  Python float, int and complex do."""
  c = flex.complex_double(1)
  for val, expected in [(np.complex64(1+2j), 1+2j), (np.float32(1.5), 1.5),
                        (np.int64(2), 2), (np.True_, 1)]:
    c[0] = val
    assert c[0] == expected, (c[0], val)
  r = flex.complex_double([1+0j]) * np.complex64(2j)
  assert isinstance(r, flex.complex_double) and list(r) == [2j], r
  r = flex.complex_double([1+0j]) * np.float32(2)
  assert isinstance(r, flex.complex_double) and list(r) == [2+0j], r

def exercise_reversed_operand_caveat(np, flex):
  """Documented caveat (see numpy_bridge.cpp): with the numpy scalar on the
  left, NumPy's own operator runs first and returns an ndarray, so the two
  operand orders give different container types."""
  d = flex.double([1.0, 3.0])
  assert isinstance(d * np.float32(2), flex.double)
  assert isinstance(np.float32(2) * d, np.ndarray)
  assert isinstance(2.0 * d, flex.double)
  assert isinstance(d > np.float32(2), flex.bool)
  assert isinstance(np.float32(2) < d, np.ndarray)

if __name__ == "__main__":
  run(args=sys.argv[1:])
