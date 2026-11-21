# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


class StudioPendingView:
    """The default ``type`` view of a model line not created yet: what the
    operations of the editor read of a view (``id``, ``model``, ``type``,
    ``name``, ``mode``), with ``line``, the model line. Its arch is the
    default arch of the line; its changes are bound to the line until Apply
    creates the view."""

    id = False
    xml_id = False
    mode = "primary"
    pending = True

    def __init__(self, line, view_type):
        self.line = line
        self.model = line.model
        self.type = view_type
        self.name = f"{line.model}.{view_type}"

    def exists(self):
        return self if self.line.exists() and not self.line.applied else None

    def __bool__(self):
        return True

    def __eq__(self, other):
        return (
            isinstance(other, StudioPendingView)
            and other.line == self.line
            and other.type == self.type
        )

    def __hash__(self):
        return hash((self.line.id, self.type))

    def __repr__(self):
        return f"StudioPendingView({self.name})"


class StudioAddedView:
    """A view a view line of a project adds to an existing model, before
    Apply creates it: what the operations of the editor read of a view
    (``id``, ``model``, ``type``, ``name``, ``mode``, ``xml_id``), with
    ``line``, the view line. Its arch is the one the line recorded; its
    changes are bound to the line until Apply creates the view. The model
    has records: every operation of the view type applies to it."""

    id = False
    mode = "primary"
    pending = False

    def __init__(self, line):
        self.line = line
        self.model = line.model
        self.type = line.view_type
        self.name = line._studio_view_name()
        self.xml_id = f"{line.project_id.module_name}.{line._studio_xml_name()}"

    def exists(self):
        return self if self.line.exists() and not self.line.applied else None

    def __bool__(self):
        return True

    def __eq__(self, other):
        return isinstance(other, StudioAddedView) and other.line == self.line

    def __hash__(self):
        return hash(("added", self.line.id))

    def __repr__(self):
        return f"StudioAddedView({self.name})"


def pending_view(line, view_type):
    return StudioPendingView(line, view_type)


def is_pending_view(view):
    return isinstance(view, StudioPendingView)


def added_view(line):
    return StudioAddedView(line)


def is_added_view(view):
    return isinstance(view, StudioAddedView)


def is_draft_view(view):
    """Whether ``view`` exists in the draft only: a pending default view of
    a model not created yet, or a view a view line adds."""
    return isinstance(view, (StudioPendingView, StudioAddedView))
