import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable, List

from asciimatics.exceptions import NextScene, ResizeScreenError, StopApplication
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.widgets import (
    Button,
    Divider,
    Frame,
    Layout,
    ListBox,
    Text,
    TextBox,
    Widget,
)
from FFmpyg.enums import StreamType
from FFmpyg.media import MediaFile, Stream


STREAM_CODEC_TYPE = "codec_type"
STREAM_CODEC_NAME = "codec_name"
STREAM_VIDEO_WIDTH = "width"
STREAM_VIDEO_HEIGHT = "height"
STREAM_AUDIO_CHANNEL_LAYOUT = "channel_layout"
STREAM_LANGUAGE = "tags.language"
STREAM_DEFAULT = "disposition.default"
THEME = "bright"


class ContactModel:
    def __init__(self):
        # Create a database in RAM.
        self._db = sqlite3.connect(":memory:")
        self._db.row_factory = sqlite3.Row

        # Create the basic contact table.
        self._db.cursor().execute(
            """
            CREATE TABLE contacts(
                id INTEGER PRIMARY KEY,
                name TEXT,
                phone TEXT,
                address TEXT,
                email TEXT,
                notes TEXT)
        """
        )
        self._db.commit()
        self.add(
            {
                "name": "Person1",
                "phone": "123",
                "address": "Nowhere",
                "email": "",
                "notes": "",
            }
        )
        self.add(
            {
                "name": "Person2",
                "phone": "123",
                "address": "Nowhere",
                "email": "",
                "notes": "",
            }
        )
        self.add(
            {
                "name": "Person3",
                "phone": "123",
                "address": "Nowhere",
                "email": "",
                "notes": "",
            }
        )

        # Current contact when editing.
        self.current_id = None

    def add(self, contact):
        self._db.cursor().execute(
            """
            INSERT INTO contacts(name, phone, address, email, notes)
            VALUES(:name, :phone, :address, :email, :notes)""",
            contact,
        )
        self._db.commit()

    def get_summary(self):
        return self._db.cursor().execute("SELECT name, id from contacts").fetchall()

    def get_contact(self, contact_id):
        return (
            self._db.cursor()
            .execute("SELECT * from contacts WHERE id=:id", {"id": contact_id})
            .fetchone()
        )

    def get_current_contact(self):
        if self.current_id is None:
            return {"name": "", "address": "", "phone": "", "email": "", "notes": ""}
        else:
            return self.get_contact(self.current_id)

    def update_current_contact(self, details):
        if self.current_id is None:
            self.add(details)
        else:
            self._db.cursor().execute(
                """
                UPDATE contacts SET name=:name, phone=:phone, address=:address,
                email=:email, notes=:notes WHERE id=:id""",
                details,
            )
            self._db.commit()

    def delete_contact(self, contact_id):
        self._db.cursor().execute(
            """
            DELETE FROM contacts WHERE id=:id""",
            {"id": contact_id},
        )
        self._db.commit()


class ListView(Frame):
    def __init__(self, screen, model):
        super(ListView, self).__init__(
            screen,
            screen.height * 2 // 3,
            screen.width * 2 // 3,
            on_load=self._reload_list,
            hover_focus=True,
            can_scroll=False,
            title="Contact List",
        )
        self.set_theme(THEME)

        # Save off the model that accesses the contacts database.
        self._model = model

        # Create the form for displaying the list of contacts.
        self._list_view = ListBox(
            Widget.FILL_FRAME,
            model.get_summary(),
            name="contacts",
            add_scroll_bar=True,
            on_change=self._on_pick,
            on_select=self._edit,
        )
        self._edit_button = Button("Edit", self._edit)
        self._delete_button = Button("Delete", self._delete)
        layout = Layout([100], fill_frame=True)
        self.add_layout(layout)
        layout.add_widget(self._list_view)
        layout.add_widget(Divider())
        layout2 = Layout([1, 1, 1, 1])
        self.add_layout(layout2)
        layout2.add_widget(Button("Add", self._add), 0)
        layout2.add_widget(self._edit_button, 1)
        layout2.add_widget(self._delete_button, 2)
        layout2.add_widget(Button("Quit", self._quit), 3)
        self.fix()
        self._on_pick()

    def _on_pick(self):
        self._edit_button.disabled = self._list_view.value is None
        self._delete_button.disabled = self._list_view.value is None

    def _reload_list(self, new_value=None):
        self._list_view.options = self._model.get_summary()
        self._list_view.value = new_value

    def _add(self):
        self._model.current_id = None
        raise NextScene("Edit Contact")

    def _edit(self):
        self.save()
        self._model.current_id = self.data["contacts"]
        raise NextScene("Edit Contact")

    def _delete(self):
        self.save()
        self._model.delete_contact(self.data["contacts"])
        self._reload_list()

    @staticmethod
    def _quit():
        raise StopApplication("User pressed quit")


class ContactView(Frame):
    def __init__(self, screen, model):
        super(ContactView, self).__init__(
            screen,
            screen.height * 2 // 3,
            screen.width * 2 // 3,
            hover_focus=True,
            can_scroll=False,
            title="Contact Details",
            reduce_cpu=True,
        )
        self.set_theme(THEME)
        # Save off the model that accesses the contacts database.
        self._model = model

        # Create the form for displaying the list of contacts.
        layout = Layout([100], fill_frame=True)
        self.add_layout(layout)
        layout.add_widget(Text("Name:", "name"))
        layout.add_widget(Text("Address:", "address"))
        layout.add_widget(Text("Phone number:", "phone"))
        layout.add_widget(Text("Email address:", "email"))
        layout.add_widget(
            TextBox(
                Widget.FILL_FRAME, "Notes:", "notes", as_string=True, line_wrap=True
            )
        )
        layout2 = Layout([1, 1, 1, 1])
        self.add_layout(layout2)
        layout2.add_widget(Button("OK", self._ok), 0)
        layout2.add_widget(Button("Cancel", self._cancel), 3)
        self.fix()

    def reset(self):
        # Do standard reset to clear out form, then populate with new data.
        super(ContactView, self).reset()
        self.data = self._model.get_current_contact()

    def _ok(self):
        self.save()
        self._model.update_current_contact(self.data)
        raise NextScene("Main")

    @staticmethod
    def _cancel():
        raise NextScene("Main")


def demo(screen, scene, contacts):
    scenes = [
        Scene([ListView(screen, contacts)], -1, name="Main"),
        Scene([ContactView(screen, contacts)], -1, name="Edit Contact"),
    ]

    screen.play(scenes, stop_on_resize=True, start_scene=scene, allow_int=True)


def main() -> None:
    """Run the CLI front-end for recode-engine"""
    contacts = ContactModel()
    last_scene = None
    while True:
        try:
            Screen.wrapper(demo, catch_interrupt=True, arguments=[last_scene, contacts])
            sys.exit()
        except ResizeScreenError as e:
            last_scene = e.scene


def load_data() -> MediaFile:
    """Loads test data"""
    test_file = Path("./has_chapters.mkv")
    assert (
        test_file.exists() and test_file.is_file()
    ), f"Can't find {test_file.resolve()}"

    return MediaFile(test_file)


def stream_short_repr(s: Stream) -> str:
    """Returns short printable representation of stream"""
    _type = StreamType(s.ffinfo[STREAM_CODEC_TYPE])
    _repr = _type.value
    if STREAM_CODEC_NAME in s.ffinfo:
        _repr += " " + s.ffinfo[STREAM_CODEC_NAME]
    if _type is StreamType.VIDEO and all(
        x in s.ffinfo for x in (STREAM_VIDEO_WIDTH, STREAM_VIDEO_HEIGHT)
    ):
        _repr += f" {s.ffinfo[STREAM_VIDEO_WIDTH]}x{s.ffinfo[STREAM_VIDEO_HEIGHT]}"
    if _type is StreamType.AUDIO and STREAM_AUDIO_CHANNEL_LAYOUT in s.ffinfo:
        _repr += " " + s.ffinfo[STREAM_AUDIO_CHANNEL_LAYOUT]
    if _type in (StreamType.AUDIO, StreamType.SUBTITLE) and STREAM_LANGUAGE in s.ffinfo:
        _repr += " " + s.ffinfo[STREAM_LANGUAGE]
    if _type in (StreamType.AUDIO, StreamType.SUBTITLE) and STREAM_DEFAULT in s.ffinfo:
        _repr += " [DEFAULT]"
    return _repr


def main_tmp() -> None:
    mf = load_data()
    print(mf)
    for idx, stream in mf.streams.items():
        assert stream.ffinfo["index"] == idx
        print(f"[{idx}] {stream_short_repr(stream)}")


ALL_RECIPE_KEYS = set()


def deep_printer(key: str, value: Any, depth: int) -> None:
    prefix = "  " * depth
    if isinstance(value, dict):
        print(prefix + key + ":")
        deep_dict_printer(value, depth + 1)
    elif isinstance(value, list):
        print(prefix + key + ":")
        deep_list_printer(value, depth + 1)
    else:
        print(prefix + key + f": {value} ({value.__class__.__name__})")


def deep_list_printer(l: list, depth: int = 0) -> None:
    for v in l:
        key = "list"
        deep_printer(key, v, depth)


def deep_dict_printer(d: dict, depth: int = 0) -> None:
    global ALL_RECIPE_KEYS
    for k, v in d.items():
        ALL_RECIPE_KEYS.add(k)
        key = f"{k} ({k.__class__.__name__})"
        deep_printer(key, v, depth)


def main_system():
    logging.basicConfig(level=logging.DEBUG, format="[%(levelname)s] %(message)s")
    import yaml

    _recipe = None
    with Path("poc.recipe.yaml").open("r", encoding="utf8") as f:
        _recipe = yaml.safe_load(f)

    # deep_dict_printer(_recipe)
    # print(f"All keys: {ALL_RECIPE_KEYS}")
    from recipe import Recipe

    recipe = Recipe(_recipe)
    _recipe_ok = recipe.recipe

    with Path("poc.recipe.validated.yaml").open("w", encoding="utf8") as f:
        yaml.safe_dump(_recipe_ok, f)

    from DRSlib.dict_utils import dict_difference

    print("diff=")
    deep_dict_printer(dict_difference(_recipe["recipe"], _recipe_ok))

    mf = load_data()
    recipe.load_arguments({})
    # recipe.validate_input(mf)
    # from DRSlib.mediainfo import MediaInfo

    # deep_dict_printer(MediaInfo().get_base_stats(mf.path))


if __name__ == "__main__":
    main_system()
