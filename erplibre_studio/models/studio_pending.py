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


def pending_view(line, view_type):
    return StudioPendingView(line, view_type)


def is_pending_view(view):
    return isinstance(view, StudioPendingView)
