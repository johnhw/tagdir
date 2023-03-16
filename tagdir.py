from pathlib import Path
import os
import sys
import json
from functools import lru_cache
from textual.app import App, ComposeResult
from textual.widgets import Footer
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Static
from textual.widgets import ListView, ListItem, Label, Input 
import hashlib
from textual.reactive import reactive
from rich.table import Table
from rich.text import Text
import random

TAG_COLORS = ["#264653", "#2A9D8F", "#E9C46A", "#F4A261", "#E76F51"]

class History(Static):
    max_lines = 6

    def on_mount(self):
        self.history = []

    def set_history(self, history):
        self.history = history
        render_table = Table(show_header=False, header_style="bold magenta", expand=True)
        render_table.add_column("Tag", style="dim", ratio=0.2)
        render_table.add_column("File", style="bright", ratio=7)
        render_table.add_column("Destination", ratio=3)        
        def color(t, c):
            return Text.from_markup(f"[{c}]{t}[/{c}]")
        for h in self.history[::-1][:self.max_lines]:
            c = get_tag_colors(h[0])
            render_table.add_row(color(h[0], c), color(str(h[1].name),c), color(str(h[2]),c))            
        self.update(render_table)


@lru_cache(1024)
def get_tag_colors(tag):
    c = int(hashlib.sha256(tag.encode()).hexdigest()
            [:4], 16) % len(TAG_COLORS)
    return TAG_COLORS[c]


class KeyLabel(Label):
    def on_key(self, event) -> None:
        self.text = event.key


class TagDir(App):
    """A Textual application that displays a list of files in the current directory,
    and allows you to move files to specified paths with a single keypress.
    """


    CSS_PATH = "tagdir.css"
    BINDINGS = [("escape", "quit", "Quit"), ("insert", "newtag", "Add/modify tag"),
                ("ctrl+z", "undo", "Undo last move"),
                ("ctrl+y", "redo", "Redo last undo"), ("ctrl+t", "TEST", "TEST")]

    def read_tags(self) -> dict:
        """Read the tags file."""
        try:
            with open("tags.json", "r") as f:
                tags = json.load(f)
        except FileNotFoundError:
            tags = {}
        return tags

    def write_tags(self):
        """Write the tags file."""
        with open("tags.json", "w") as f:
            json.dump(self.tags, f)

    def init(self):
        """Initialize the application."""
        self.tags = self.read_tags()
        self.base_path = Path.cwd() if len(sys.argv) == 1 else Path(sys.argv[1])        
        self.history = []
        self.redo_history = []
        self.file_cache = reactive([])

    
    def init_paths(self):
        """Initialize the paths."""
        self.files = [p for p in Path.glob(self.base_path, "*") if p.is_file()]   
        self.file_names = [f.name for f in self.files]
        self.file_cache = [ListItem(Label(f.name)) for f in self.files]
        self.file_list = ListView(*self.file_cache)        

    def make_tag_label(self, t):
        """Make a tag label, with the auto-colouring enabled."""
        c = get_tag_colors(t)
        item = ListItem(Label(f"[{c}][bold]({t})[/bold] {self.tags[t]}[/{c}]"))
        item.tag = t
        item.tag_name = self.tags[t]
        return item

    def make_history_label(self, h):
        """Make a history label."""
        return ListItem(Label(f"{h}"))

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""

        self.init()
        # can be "none", "newtag", "newtag2"
        self.key_mode = "none"
        self.action_label = Label("---", classes="action-label")
        yield self.action_label

        self.file_list = ListView(classes='file-list')
        self.init_paths()
        
        self.taglist = ListView(classes='tag-list')
        self.update_tags()
        self.history_widget = History(classes="history-list")
        yield Horizontal(Vertical(Vertical(Label("Files", classes="section-label"), self.file_list, classes="box"),  classes="column"),
                         Vertical(Vertical(Label("Tags", classes="section-label"), self.taglist, classes="box"),
                                  Vertical(Label("History", classes="section-label"), self.history_widget, classes="box"),  classes="column"))
        yield Footer()

    def update_tags(self):
        self.taglist.clear()
        for tag in self.tags:
            self.taglist.append(self.make_tag_label(tag))
        self.write_tags()

    def action_TEST(self):
        fname = "".join([random.choice("abcdefghijklmnopqrstuvwxyz") for i in range(8)]) + ".txt"
        with open(fname, "w") as f:
            f.write("TEST")
        self.init_paths()    

    def on_key(self, event):
        if self.key_mode=="none":
            for tag in self.tags:           
                    if event.key == tag:
                        file = self.files[self.file_list.index]                                  
                        self.move_file(tag, file, self.tags[tag])
        if self.key_mode=="newtag":
            if event.key == "escape":
                self.key_mode = "none"
                self.update_status("Aborted")    
                self.key_input.remove()         
                event.prevent_default()
            else:
                k = str(event.key)                    
                self.keyname.update(k)
                self.keyname.text = k 
                if k in self.tags:
                    self.tagname.value = self.tags[k]
                self.tagname.focus()
                self.key_mode = "newtag2"
                event.prevent_default()
                    
    def on_input_submitted(self, message):                
        self.key_mode = "none"   
        tag_key = self.keyname.text  
        tag_path = self.tagname.value  
        c = get_tag_colors(tag_key)
        if tag_path=="":            
            self.update_status(f"Deleted tag: ([bold][{c}]{tag_key}[/{c}][/bold])")
            del self.tags[tag_key]
        else:
            self.tags[tag_key] = tag_path     
            if tag_key in self.tags:
                self.update_status(f"Updated tag: ([bold][{c}]{tag_key}[/{c}][/bold]) [{c}]{self.tags[tag_key]}[/{c}]")
            else:
                self.update_status(f"Added tag: ([bold][{c}]{tag_key}[/{c}][/bold]) [{c}]{self.tags[tag_key]}[/{c}]")
                
        
        
        self.update_tags()
        self.key_input.remove()

    def move(self, file, dest):
        
        try:
            os.rename(self.base_path / Path(file), self.base_path / Path(dest))
        except OSError:
            self.update_status(f"[red] Error moving file: {file.name} to {dest} [/red]")
            return False        
        self.file_list.focus()
        return True

    def move_file(self, tag, file, dest):
        if not (Path(self.base_path) / Path(dest)).exists():
            (Path(self.base_path) / Path(dest)).mkdir(parents=True, exist_ok=True)            
        success = self.move(file, Path(dest) / Path(file.name))
        if success:
            
            ix = self.file_names.index(file.name)
            elt = self.file_cache[ix]
            elt.remove()
            self.file_cache.pop(ix)
            self.file_names.pop(ix)
            self.files.pop(ix)
            self.history.append([tag, file, dest])
            self.history_widget.set_history(self.history)
            self.file_list.index = ix
            self.file_list.post_message_no_wait(ListView.Highlighted(self.file_list, ix))
            c = get_tag_colors(tag)
            self.update_status(f"([bold][{c}]{tag}[/{c}][/bold]) {file} -> [{c}]{self.tags[tag]}[/{c}]")      
        
        
    def on_mount(self):
        self.file_list.focus()

    def action_quit(self) -> None:
        exit(0)

    def update_status(self, status):
        self.action_label.update(status)
        self.action_label.styles.background = "white"
        self.action_label.styles.animate("background", value=self.action_label._css_styles.background, duration=0.2)

    def action_undo(self) -> None:
        if len(self.history)>0:
            last = self.history[-1]
            success = self.move(Path(last[2]) / Path(last[1].name), Path(last[1]))            
            if success:
                self.update_status(f"Undo: {last[1]} <- {last[2]}")
                self.history.pop()
                self.redo_history.append(last)   
                self.history_widget.set_history(self.history)   
                self.file_list.focus()                                     
        else:
            self.update_status("No more history to undo.")

    def action_redo(self):
        if len(self.redo_history)>0:
            last = self.redo_history[-1]
            success = self.move(Path(last[1]), Path(last[2]) / Path(last[1].name))            
            if success:
                self.update_status(f"Redo: {last[1]} -> {last[2]}")
                self.redo_history.pop()
                self.history.append(last)            
                self.history_widget.set_history(self.history)
                self.file_list.focus()
        else:
            self.update_status("No more history to redo.")

    def action_newtag(self) -> None:    
        self.key_mode = "newtag"        
        self.tagname = Input(id="tagname", placeholder="[tag name]", classes="tagname")
        self.keyname = Label("Key?", id="keyname", classes="keyname")
        self.key_input = Horizontal(self.keyname, self.tagname)
        self.mount(self.key_input, before=self.action_label)
        self.keyname.focus()


def launch_tagdir():
    """Launch the app."""
    t = TagDir()
    t.run()


if __name__ == "__main__":
    launch_tagdir()
