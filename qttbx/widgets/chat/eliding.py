"""Text widgets that shrink instead of flooring the layout.

A widget that reports its full text width as its ``minimumSizeHint`` pins the
minimum width of every container it sits in. In the chat UI that chain ends at
the ConversationView -- a ``setWidgetResizable`` QScrollArea whose whole job is
to let the bubbles track the window -- and at the ChatWindow itself. So one
long string anywhere (a title, a model id, a question header, an option
description, an MCP tool name, a tool status) stops the bubbles tracking the
window, raises a horizontal scrollbar, and leaves the window refusing to be
resized back down. A force-killed Coot bridge produced exactly that: its
~230-char MCP connection error reached a tool disclosure header.

None of that text is bounded in practice -- it comes from the model, from the
user's ``--model``, or from a tool server -- so a character budget cannot fix
it: 60 characters of a proportional font is still ~880 px. These widgets bound
the *pixels* instead:

- ``minimumSizeHint`` width 0, so the widget never floors its container;
- a horizontal size policy that can shrink, since a QSizePolicy of ``Minimum``
  (the QCheckBox / QRadioButton default) makes the layout treat ``sizeHint``
  as the floor and ignore ``minimumSizeHint`` entirely;
- ``sizeHint`` reporting the FULL text's width, so a layout with room still
  hands the widget its natural width -- the widget holds an *elided* copy of
  the text, and Qt would otherwise derive the hint from that copy and never
  grow it back;
- the text elided to whatever width the widget actually gets, re-elided from
  the widget's own ``resizeEvent``, which fires whenever the layout changes its
  width -- not only when the window is resized. Hooking a container's
  ``resizeEvent`` instead misses a sibling appearing and taking the width.

Use ``WrappingLabel`` for prose, which should wrap rather than elide. Word wrap
alone does not unfloor a label -- a wrapped QLabel's ``minimumSizeHint`` width
is its widest *unbreakable token*, so a lone path or identifier floors it just
as the whole string would -- so it needs the same zeroed minimumSizeHint.
"""

import html

from qttbx.qt import QtCore, QtGui, QtWidgets

# A few pixels of breathing room added to a hugging widget's natural width, so
# the text is never painted hard against the edge and never sits exactly on the
# rounding boundary where the last glyph would elide.
_HUG_SLACK = 3


class _ElideMixin(object):
  """Elide-to-fit behaviour shared by the label and button variants.

  Mixed in ahead of exactly one Qt text-widget base (QLabel, QToolButton,
  QCheckBox, QRadioButton), so ``super()`` in these methods resolves to that
  base. Subclasses must call ``_init_elide`` from their ``__init__``.
  """

  def _init_elide(self, mode=QtCore.Qt.ElideRight, keep=0):
    self._full_text = ""
    self._elide_mode = mode
    self._keep = keep
    self._tooltip_override = None
    # Make the widget shrinkable and change nothing else. Without ShrinkFlag a
    # layout treats sizeHint as the floor and never consults minimumSizeHint,
    # so zeroing that hint would do nothing at all (QCheckBox / QRadioButton
    # default to Minimum, QToolButton to Fixed -- none of them can shrink).
    #
    # OR the flag into whatever the base chose rather than imposing one policy
    # on all of them: each default carries intent. QToolButton is Fixed so it
    # hugs its text, and its autoRaise hover highlight covers the text and no
    # more; blanket-setting Preferred hands it a GrowFlag it never had and
    # stretches the header across the whole bubble. Fixed|Shrink is Maximum
    # (hug, but yield when squeezed), Minimum|Shrink is Preferred, and a
    # QLabel is already Preferred and comes through untouched.
    policy = self.sizePolicy()
    policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Policy(
      int(policy.horizontalPolicy()) | int(QtWidgets.QSizePolicy.ShrinkFlag)))
    self.setSizePolicy(policy)

  # ---- public API ---------------------------------------------------------

  def set_full_text(self, text, tooltip=None):
    """Set the text to render, elided to whatever width the widget gets.

    Parameters
    ----------
    text : str
        Text to display. Coerced with ``str``, so a caller may pass an
        exception or any other object without crashing the render.
    tooltip : str, optional
        Tooltip to show in place of the default rule, which carries the full
        text only when the elide actually dropped something. Pass this when
        ``text`` is itself already an abbreviation of something longer, so
        the default rule cannot see what was lost: a tool disclosure header
        shortens a long status before it ever gets here, and puts the whole
        of it on the tooltip.
    """
    self._full_text = "" if text is None else str(text)
    self._tooltip_override = None if tooltip is None else str(tooltip)
    # A screen reader gets the whole string: with no accessible name Qt
    # falls back to the rendered text, which may be "Alway…". Markup a
    # label renders is stripped first, or the reader gets the tags --
    # and only then: the same strip of a string the label shows as it
    # is folds its newlines and swallows a "<module>".
    self.setAccessibleName(
      QtGui.QTextDocumentFragment.fromHtml(self._full_text).toPlainText()
      if self._renders_as_rich_text(self._full_text)
      else self._full_text)
    self.updateGeometry()
    self._apply_elide()

  def full_text(self):
    """Return the untruncated text, regardless of what is rendered."""
    return self._full_text

  # ---- Qt overrides -------------------------------------------------------

  def sizeHint(self):
    """Report the FULL text's width as the natural width.

    The widget holds an elided copy of the text, so the inherited hint would
    track the elision and the layout would never give the width back. A
    hugging widget (a QToolButton, a checkbox) is handed exactly this width,
    so it has to be enough to render the whole text: measured with the same
    metric the elide uses, plus a few px of slack so the last glyph never
    lands on the rounding boundary and gets dropped.
    """
    return QtCore.QSize(
      self._text_width(self._full_text) + self._chrome_width() + _HUG_SLACK,
      super().sizeHint().height())

  def minimumSizeHint(self):
    """Never floor the container -- the whole point of this class -- or
    by the width of its kept characters, when it was given some."""
    return QtCore.QSize(self._floor_width(),
                        super().minimumSizeHint().height())

  def resizeEvent(self, event):
    super().resizeEvent(event)
    self._apply_elide()

  def showEvent(self, event):
    super().showEvent(event)
    self._apply_elide()

  # ---- internals ----------------------------------------------------------

  def _text_width(self, text):
    """Width one line of ``text`` occupies, as the elide and painter see it.

    ``elidedText`` keeps a string whole exactly while the budget is at least
    this, which ``QFontMetrics.horizontalAdvance`` (rounded down) can undercut
    by a pixel -- enough to drop the last glyph at the hug boundary. Measuring
    both the hint and the elide with this one metric keeps them consistent.
    """
    return self.fontMetrics().size(QtCore.Qt.TextSingleLine, text).width()

  def _chrome_width(self):
    """Width this widget adds around its text: margins, frame, indicator."""
    return max(0, super().sizeHint().width()
               - self._text_width(self.text()))

  def _floor_width(self):
    """The width of the ``keep`` characters this widget never drops.

    Zero without any. Otherwise what the elide leaves at that count --
    the head of the text and an ellipsis under ElideRight, the tail
    under ElideLeft, both ends under ElideMiddle -- measured as
    ``sizeHint`` measures the whole, and never more than the whole.
    """
    keep, full = self._keep, self._full_text
    if keep <= 0 or not full:
      return 0
    if len(full) <= keep:
      return self.sizeHint().width()
    mode = self._elide_mode
    if mode == QtCore.Qt.ElideLeft:
      kept = "…" + full[len(full) - keep:]
    elif mode == QtCore.Qt.ElideMiddle:
      head, tail = (keep + 1) // 2, keep // 2
      kept = full[:head] + "…" + full[len(full) - tail:]
    elif mode == QtCore.Qt.ElideNone:
      return self.sizeHint().width()
    else:
      kept = full[:keep] + "…"
    return self._text_width(kept) + self._chrome_width() + _HUG_SLACK

  def _apply_elide(self):
    self.setText(self._elided_text())
    self._apply_tooltip(self.text())

  def _elided_text(self):
    """The full text cut down to the width the widget actually has."""
    # Until it is laid out, the widget's width is a Qt default (100 px for a
    # fresh QLabel), not an assigned one -- eliding against that would cut
    # text that is about to have room. Hold the full text instead: the zeroed
    # minimumSizeHint means it still cannot floor anything meanwhile, and the
    # resizeEvent / showEvent from the first layout pass re-elides it against
    # the real width.
    if not self.isVisible():
      return self._full_text
    available = self.width() - self._chrome_width()
    # Show the whole text once it fits, rather than leaning on elidedText at
    # the boundary: at equal width elidedText can still drop the last glyph to
    # its ellipsis, which is the '(finishe…' this guards against.
    if available >= self._text_width(self._full_text):
      return self._full_text
    # Never the empty string for a text that has something to show.
    # _chrome_width measures around the CURRENT text, and a QCheckBox with
    # no text drops its label margin (and six px of height): the chrome
    # shrinks, the next budget fits an ellipsis, the chrome grows back, the
    # ellipsis no longer fits -- and the text flips between '' and '…' on
    # every pass, a resize loop at 100% CPU in a band of widths just above
    # the indicator's. An ellipsis the widget cannot fit is clipped, and
    # still carries the full text on the tooltip. An empty full text stays
    # empty: an icon-only button must not grow an ellipsis.
    return (self.fontMetrics().elidedText(
      self._full_text, self._elide_mode, available)
      or ("…" if self._full_text else ""))

  def _apply_tooltip(self, elided):
    if self._tooltip_override is not None:
      self.setToolTip(self._as_tooltip(self._tooltip_override))
      return
    # Only carry a tooltip when something was actually dropped, so an
    # ordinary short label doesn't sprout a redundant hover label.
    self.setToolTip(self._as_tooltip(self._full_text)
                    if elided != self._full_text else "")

  def _as_tooltip(self, text):
    """``text`` as a tooltip that reads the way this widget renders it.

    A tooltip auto-detects rich text, so markup in a string the widget
    shows literally -- a button's text is always plain, a QLabel's when
    its format says so -- would render on hover: a tool name that the
    approval card is careful to display verbatim. Convert such a string
    to escaped HTML, its whitespace kept: a bare ``<p>`` folded the
    indentation of a traceback a disclosure puts here, and its newlines.
    Ordinary text is left alone, so it stays comparable.
    """
    if self._renders_as_rich_text(text) or not _could_be_markup(text):
      return text
    return ('<p style="white-space:pre-wrap">%s</p>'
            % html.escape(text, quote=False))

  def _renders_as_rich_text(self, text):
    """Whether this widget shows the markup in ``text`` as formatting:
    a QLabel told to, or one left to decide that decides as Qt does."""
    if not isinstance(self, QtWidgets.QLabel):
      return False
    fmt = self.textFormat()
    if fmt == QtCore.Qt.AutoText:
      return _might_be_rich_text(text)
    return fmt != QtCore.Qt.PlainText


def _could_be_markup(text):
  """Whether a tooltip might take ``text`` for rich text.

  A superset of Qt's test, which looks no further than the first line
  for a tag it knows or a literal ``&lt;``: escaping a string Qt would
  have shown literally anyway costs at most a tooltip that word-wraps,
  while a leaked tag renders. The exact test below is for where
  erring the other way costs something too.
  """
  return "<" in text or "&" in text


# The tags Qt::mightBeRichText knows, QTextHtmlParser's element table.
_HTML_ELEMENTS = frozenset("""
  a address b big blockquote body br caption center cite code dd dfn div dl
  dt em font h1 h2 h3 h4 h5 h6 head hr html i img kbd li link meta nobr ol
  p pre qt s samp script small span strong style sub sup table tbody td
  tfoot th thead title tr tt u ul var""".split())


def _might_be_rich_text(text):
  """Whether Qt, left to decide, takes ``text`` for rich text.

  ``Qt::mightBeRichText``, as a QLabel with the AutoText format and a
  tooltip apply it: a ``<!DOCTYPE``, or on the first line and ahead of
  any ``<``, a literal ``&lt;``, or a tag Qt knows. Ported rather than
  called, since the bindings expose it under a name
  (``QtGui.Qt.mightBeRichText``) checked here only for PySide2;
  tst_chat_eliding compares the two where both exist.
  """
  n = len(text)
  i = 0
  while i < n and text[i].isspace():
    i += 1
  if text[i:i + 5] == "<?xml":          # as for xhtml; skip the prolog
    while i < n:
      if text[i] == "?" and i + 2 < n and text[i + 1] == ">":
        i += 2
        break
      i += 1
    while i < n and text[i].isspace():
      i += 1
  if text[i:i + 5].lower() == "<!doc":
    return True
  while i < n and text[i] not in "<\n":
    if text[i] == "&" and text[i + 1:i + 4] == "lt;":
      return True                       # a desperate attempt at a <...>
    i += 1
  if i < n and text[i] == "<":
    close = text.find(">", i)
    if close > -1:
      tag = ""
      for j in range(i + 1, close):
        c = text[j]
        if c.isalnum():
          tag += c
        elif tag and c.isspace():
          break
        elif tag and c == "/" and j + 1 == close:
          break
        elif not c.isspace() and (tag or c != "!"):
          return False                  # that's not a tag
      return tag.lower() in _HTML_ELEMENTS
  return False


class ElidingLabel(_ElideMixin, QtWidgets.QLabel):
  """QLabel that elides its text to fit and never floors its container.

  Parameters
  ----------
  parent : QtWidgets.QWidget, optional
      Parent widget.
  mode : QtCore.Qt.TextElideMode, optional
      Where to drop characters. ``ElideLeft`` keeps the tail visible, which
      is what a path wants.
  keep : int, optional
      Characters the label always has room for, so that it floors its
      container by their width rather than by nothing: for a label whose
      first few characters are the signal -- the kind of a tool's source
      -- and must outlast any squeeze. Under ElideRight they are the
      head of the text; under ElideLeft the tail; under ElideMiddle both
      ends. Zero, the default, floors nothing.
  """

  def __init__(self, parent=None, mode=QtCore.Qt.ElideRight, keep=0):
    super().__init__(parent)
    self._init_elide(mode, keep)


class ElidingToolButton(_ElideMixin, QtWidgets.QToolButton):
  """QToolButton that elides its text to fit and never floors its container."""

  def __init__(self, parent=None, mode=QtCore.Qt.ElideRight):
    super().__init__(parent)
    self._init_elide(mode)


class ElidingCheckBox(_ElideMixin, QtWidgets.QCheckBox):
  """QCheckBox that elides its text to fit and never floors its container."""

  def __init__(self, parent=None, mode=QtCore.Qt.ElideRight):
    super().__init__(parent)
    self._init_elide(mode)


class ElidingRadioButton(_ElideMixin, QtWidgets.QRadioButton):
  """QRadioButton that elides its text and never floors its container."""

  def __init__(self, parent=None, mode=QtCore.Qt.ElideRight):
    super().__init__(parent)
    self._init_elide(mode)


class WrappingLabel(QtWidgets.QLabel):
  """QLabel that wraps prose and still never floors its container.

  Word wrap on its own is not enough: a wrapped QLabel reports its widest
  unbreakable token as its ``minimumSizeHint`` width, so a single long path,
  URL, or snake_case identifier floors the container exactly as the whole
  string would. Prose belongs here -- wrapped and fully readable. A tag, an
  id, or anything that must stay on one line belongs in ``ElidingLabel``.

  Parameters
  ----------
  text : str, optional
      Initial text.
  parent : QtWidgets.QWidget, optional
      Parent widget.
  """

  def __init__(self, text="", parent=None):
    super().__init__(text, parent)
    self.setWordWrap(True)

  def minimumSizeHint(self):
    """Zero width: the wrapped text reflows to whatever width it is given."""
    return QtCore.QSize(0, super().minimumSizeHint().height())
