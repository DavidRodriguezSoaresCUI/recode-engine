import logging
import sqlite3
import sys
from collections import deque
from pathlib import Path
from typing import Any, Callable, List, Tuple

from asciimatics.exceptions import NextScene, ResizeScreenError, StopApplication
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.widgets import (
    Button,
    Divider,
    Frame,
    Label,
    Layout,
    ListBox,
    Text,
    TextBox,
    Widget,
)


STREAM_CODEC_TYPE = "codec_type"
STREAM_CODEC_NAME = "codec_name"
STREAM_VIDEO_WIDTH = "width"
STREAM_VIDEO_HEIGHT = "height"
STREAM_AUDIO_CHANNEL_LAYOUT = "channel_layout"
STREAM_LANGUAGE = "tags.language"
STREAM_DEFAULT = "disposition.default"
THEME = "bright"

SCREEN_MAIN_MENU = "Main Menu"
SCREEN_RECIPE_MANAGER = "Recipe Manager"
SCREEN_CREATE_NEW_JOB = "Create new transcode job"
SCREEN_LOAD_JOB = "Load existing transcode job"
SCREEN_SHOW_INFO = "Show info"

SCENE_STACK = deque()

LOG = logging.getLogger(__name__)


def go_to_next_scene(current_scene: str, next_scene: str) -> None:
    '''Helper function to change scenes in a way that allows to go back to previous scenes'''
    global SCENE_STACK
    SCENE_STACK.append(current_scene)
    raise NextScene(next_scene)


def go_to_previous_scene() -> None:
    '''Helper function to go back to the previous scene'''
    global SCENE_STACK
    raise NextScene(SCENE_STACK.pop())


def resolve_listbox_selection_label(options: List[Tuple[str, int]], id: int) -> str:
    '''Resolve the selected label in a listbox given its id'''
    for o in options:
        if o[1] == id:
            return o[0]
    raise ValueError(f"Can't resolve id {id} given options {options}")


class NonRootFrame(Frame):
    '''All non-root frames require a way to return to previous frame. Requires a button that calls _return()'''

    @staticmethod
    def _return():
        go_to_previous_scene()


class ShowInfo(NonRootFrame):
    '''Equivalent of the "about" window on GUI apps'''

    def __init__(self, screen) -> None:
        '''Set up screen'''
        super().__init__(
            screen,
            screen.height,
            screen.width,
            hover_focus=True,
            can_scroll=False,
            title=SCREEN_SHOW_INFO,
        )
        self.set_theme(THEME)

        content_layout = Layout(columns=[100], fill_frame=True)
        self.add_layout(content_layout)
        content_layout.add_widget(Label("Author: DRScui"))
        content_layout.add_widget(Label("Author: DRScui"))

        
        footer = Layout([100])
        self.add_layout(footer)
        footer.add_widget(Divider())
        footer.add_widget(Button('Return', self._return))

        self.fix()


class MainMenu(Frame):
    '''Main menu (and "root") screen
    Displays program name and allows to select uses (see USES)
    '''

    USES = [
        (SCREEN_RECIPE_MANAGER, 0),
        (SCREEN_CREATE_NEW_JOB, 1),
        (SCREEN_LOAD_JOB, 2),
        (SCREEN_SHOW_INFO, 3)
    ]

    def __init__(self, screen) -> None:
        '''Set up screen'''
        super().__init__(
            screen,
            screen.height,
            screen.width,
            hover_focus=True,
            can_scroll=False,
            title=SCREEN_MAIN_MENU,
        )
        self.set_theme(THEME)

        self._list_view = ListBox(
            Widget.FILL_FRAME,
            MainMenu.USES,
            name="uses",
            add_scroll_bar=False,
            on_select=self._on_select,
        )
        self._exit_button = Button('Exit', self._exit)

        uses_list = Layout([100], fill_frame=True)
        self.add_layout(uses_list)
        uses_list.add_widget(self._list_view)
        
        footer = Layout([100])
        self.add_layout(footer)
        footer.add_widget(Divider())
        footer.add_widget(self._exit_button)

        self.fix()

    def _on_select(self, *args, **kwargs) -> None:
        next_screen = resolve_listbox_selection_label(MainMenu.USES, self._current_use)
        LOG.info(f"MainMenu._on_select self._current_use={self._current_use} => next_screen='{next_screen}'")
        go_to_next_scene(SCREEN_MAIN_MENU, next_screen)

    @property
    def _current_use(self) -> int:
        if self._list_view.value is None:
            raise ValueError("Can't read currently selected list item")
        return self._list_view.value

    @staticmethod
    def _exit():
        raise StopApplication("User pressed exit")


# class ListView(Frame):
#     def __init__(self, screen, model):
#         super(ListView, self).__init__(
#             screen,
#             screen.height,
#             screen.width,
#             on_load=self._reload_list,
#             hover_focus=True,
#             can_scroll=False,
#             title="Contact List",
#         )
#         self.set_theme(THEME)

#         # Save off the model that accesses the contacts database.
#         self._model = model

#         # Create the form for displaying the list of contacts.
#         self._list_view = ListBox(
#             Widget.FILL_FRAME,
#             model.get_summary(),
#             name="contacts",
#             add_scroll_bar=True,
#             on_change=self._on_pick,
#             on_select=self._edit,
#         )
#         self._edit_button = Button("Edit", self._edit)
#         self._delete_button = Button("Delete", self._delete)
#         layout = Layout([100], fill_frame=True)
#         self.add_layout(layout)
#         layout.add_widget(self._list_view)
#         layout.add_widget(Divider())
#         layout2 = Layout([1, 1, 1, 1])
#         self.add_layout(layout2)
#         layout2.add_widget(Button("Add", self._add), 0)
#         layout2.add_widget(self._edit_button, 1)
#         layout2.add_widget(self._delete_button, 2)
#         layout2.add_widget(Button("Quit", self._quit), 3)
#         self.fix()
#         self._on_pick()

#     def _on_pick(self):
#         self._edit_button.disabled = self._list_view.value is None
#         self._delete_button.disabled = self._list_view.value is None

#     def _reload_list(self, new_value=None):
#         self._list_view.options = self._model.get_summary()
#         self._list_view.value = new_value

#     def _add(self):
#         self._model.current_id = None
#         raise NextScene("Edit Contact")

#     def _edit(self):
#         self.save()
#         self._model.current_id = self.data["contacts"]
#         raise NextScene("Edit Contact")

#     def _delete(self):
#         self.save()
#         self._model.delete_contact(self.data["contacts"])
#         self._reload_list()

#     @staticmethod
#     def _quit():
#         raise StopApplication("User pressed quit")


def demo(screen: Screen, scene):
    scenes = [
        Scene([MainMenu(screen)], -1, name=SCREEN_MAIN_MENU),
        Scene([ShowInfo(screen)], -1, name=SCREEN_SHOW_INFO)
    ]
    screen.play(scenes, stop_on_resize=True, start_scene=scene, allow_int=True)


def main() -> None:
    """Run the CLI front-end for recode-engine"""
    last_scene = None
    while True:
        try:
            Screen.wrapper(demo, catch_interrupt=True, arguments=[last_scene])
            sys.exit()
        except ResizeScreenError as e:
            last_scene = e.scene



if __name__ == "__main__":
    logging.basicConfig(filename='recode-engine.log', filemode='w', level=logging.INFO)
    main() # main_system()
