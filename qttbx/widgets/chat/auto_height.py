"""Make a QTextEdit-family widget grow to fit its content.

The chat view's outer QScrollArea (ConversationView) is the sole
scrollable surface — per-bubble text widgets that grow their own
scrollbars stack visually badly and force the user to scroll twice
to read a long message. set_auto_height(widget) reconfigures the
widget so its height tracks the document height as content changes
and as the widget's width changes (the available wrap width).
"""

import math

from qttbx.qt import QtCore, QtGui, QtWidgets


def set_auto_height(widget, min_lines=1):
  """Configure a text widget to grow with its content instead of scrolling.

  Applies to ``QTextEdit`` / ``QPlainTextEdit`` / ``QTextBrowser``. The
  effects are:

  - Both scrollbars disabled (the outer scroll area handles it).
  - Vertical size policy = Fixed, horizontal = Expanding.
  - Any existing maximumHeight constraint is lifted.
  - On document changes, the widget's height is set to the document's
    current rendered height (plus the frame chrome).
  - On viewport resize (wrap width changes), the height is recomputed
    because long lines may re-wrap.

  Parameters
  ----------
  widget : QtWidgets.QTextEdit
      The text widget to reconfigure (also accepts ``QPlainTextEdit``
      and ``QTextBrowser``).
  min_lines : int, optional
      Clamps the minimum rendered height to N text lines so an empty
      widget doesn't collapse to zero pixels mid-stream.
  """
  widget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
  widget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
  widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                       QtWidgets.QSizePolicy.Fixed)
  widget.setMaximumHeight(16777215)   # Qt's QWIDGETSIZE_MAX -- "no cap"

  def _refresh():
    doc = widget.document()
    # Wrap at the current viewport width so height tracks reality.
    viewport_w = widget.viewport().width()
    if viewport_w > 0:
      doc.setTextWidth(viewport_w)
    frame = 2 * widget.frameWidth()
    line_h = widget.fontMetrics().lineSpacing()
    # QPlainTextEdit uses QPlainTextDocumentLayout, whose
    # documentSize().height() returns the BLOCK count, not pixels --
    # so a 30-line plain-text document reports height 30.0 instead of
    # ~30 * lineSpacing. Sum block bounding rects for an accurate,
    # wrap-aware pixel height. QTextEdit and QTextBrowser use the
    # default QTextDocumentLayout which reports pixel heights directly.
    if isinstance(widget, QtWidgets.QPlainTextEdit):
      layout = doc.documentLayout()
      doc_h = 0
      block = doc.firstBlock()
      while block.isValid():
        doc_h += layout.blockBoundingRect(block).height()
        block = block.next()
      # The block rects carry the document's bottom margin but not its
      # top one, and QPlainTextEdit counts the last line as visible
      # only once the viewport holds it whole, top margin included.
      # Short of that it keeps a one-line scroll range: a wheel notch,
      # PageDown or Space over the view then shifts its text up a line
      # instead of scrolling the conversation. Round up -- a fraction
      # short is still short.
      doc_h = int(math.ceil(doc_h + doc.documentMargin()))
    else:
      doc_h = int(doc.size().height())
    min_h = max(min_lines, 1) * line_h + frame
    was = widget.height()
    widget.setFixedHeight(max(doc_h + frame + 2, min_h))
    # A hidden widget's show delivers its pending resizes in order; a
    # visible one's viewport can be left behind (see _sync_viewport).
    if widget.height() != was and widget.isVisible():
      _sync_viewport(widget)

  widget.document().contentsChanged.connect(_refresh)

  # Hook the resize event so width-driven rewrap recomputes the height.
  # Wrapping the bound method (rather than subclassing) keeps the
  # helper usable on existing widget subclasses without forcing a
  # new class per text-widget kind. QAbstractScrollArea delivers
  # resizeEvent for its VIEWPORT's resize, once its own has set the
  # wrap width -- which is why the hook sits here and not ahead of it.
  _orig_resize = widget.resizeEvent

  def _resize_event(event):
    _orig_resize(event)
    _refresh()

  widget.resizeEvent = _resize_event

  # Initial sizing so the widget isn't a 0-px sliver before the first
  # contentsChanged fires.
  _refresh()

  # Expose the refresh callable so a caller that opens a folded body can
  # re-measure it at once (DisclosureRow.set_expanded does it before
  # returning). The resize hook above re-measures whenever the layout
  # gives the widget a new width -- before the first one a QTextEdit wraps
  # at Qt's 100 px default width (far too tall) and a QPlainTextEdit does
  # not wrap at all (too short once its lines wrap) -- but a body that
  # reopens at the width it had gets no resize event, so a font change
  # made while it was folded is picked up only by this refresh.
  widget._auto_height_refresh = _refresh


def _sync_viewport(widget):
  """Bring ``widget``'s viewport up to a height just set from inside
  its own resize event.

  That event is the viewport's, delivered from inside the scroll
  area's child layout or, on first show, before the viewport is
  visible; so the widget resizes but the viewport is left behind on
  one of two counts. The child layout guards against re-entry and
  keeps the viewport's old geometry: a preview that grew by two lines
  on rewrap showed its first three. A LayoutRequest runs that layout
  again, unguarded. And a viewport not yet visible has its resize only
  marked pending, with the scrollbar range computed for the old height
  left standing -- the whole document minus a line, for a wheel notch
  to scroll. Deliver that pending resize now, as its show would have.
  """
  QtCore.QCoreApplication.sendEvent(
    widget, QtCore.QEvent(QtCore.QEvent.LayoutRequest))
  viewport = widget.viewport()
  if viewport.testAttribute(QtCore.Qt.WA_PendingResizeEvent):
    viewport.setAttribute(QtCore.Qt.WA_PendingResizeEvent, False)
    QtCore.QCoreApplication.sendEvent(
      viewport, QtGui.QResizeEvent(viewport.size(), QtCore.QSize(-1, -1)))


def set_transparent_background(view):
  """Make a text view paint no background of its own, theme-switch safe.

  The obvious recipe -- ``setStyleSheet("background: transparent;")`` --
  has a Qt 5.15 trap: once a stylesheet-styled view has been polished,
  it can keep the palette the stylesheet engine resolved for it, so an
  OS light/dark switch afterwards leaves its text at the OLD theme's
  colour. Setting the ``Base`` role transparent on the widget's own
  palette pins only that role; ``Text`` keeps inheriting, so the view
  follows the app palette like an unstyled widget.

  Parameters
  ----------
  view : QtWidgets.QAbstractScrollArea
      A QPlainTextEdit / QTextEdit style view.
  """
  palette = view.palette()
  palette.setColor(QtGui.QPalette.Base, QtCore.Qt.transparent)
  view.setPalette(palette)
  view.viewport().setAutoFillBackground(False)


def plain_text_view(parent=None, fixed_pitch=False):
  """A read-only, frameless, backgroundless QPlainTextEdit that grows
  with its content: the chat's one recipe for a block of verbatim text,
  so a tool's arguments and result and an approval card's argument
  preview all behave alike.

  Lines wrap at a word boundary or, failing that, anywhere -- a
  QPlainTextEdit's default, set here so the recipe says so -- and an
  unbreakable token (a sequence, a path) wraps onto further lines
  rather than running off behind the horizontal scrollbar that
  ``set_auto_height`` has switched off. No explicit text colour: the
  text follows the active theme's palette, where a hardcoded grey went
  near-invisible on dark themes.

  Parameters
  ----------
  parent : QtWidgets.QWidget, optional
      Parent widget.
  fixed_pitch : bool, optional
      Use the platform's fixed-pitch font (for JSON arguments). Resolved
      through QFontDatabase rather than a 'monospace' stylesheet: Qt has
      no font literally named "Monospace" on macOS / Windows, so the CSS
      generic forces a one-time ~50 ms alias scan and prints a
      qt.qpa.fonts warning. ``systemFont(FixedFont)`` returns Menlo on
      macOS, Consolas on Windows, etc.

  Returns
  -------
  QtWidgets.QPlainTextEdit
  """
  view = QtWidgets.QPlainTextEdit(parent)
  view.setReadOnly(True)
  view.setFrameStyle(QtWidgets.QFrame.NoFrame)
  view.setWordWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
  if fixed_pitch:
    view.setFont(QtGui.QFontDatabase.systemFont(
      QtGui.QFontDatabase.FixedFont))
  set_transparent_background(view)
  set_auto_height(view)
  return view
