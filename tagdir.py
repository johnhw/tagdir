from pathlib import Path 
import pathlib 
import os
import sys
import json
import colorsys
import random 
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

TAG_COLORS = []

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



@lru_cache(None)
def get_tag_colors(tag):
    """Hash a tag, then convert it to a color."""
    seed = int(hashlib.sha256(tag.encode()).hexdigest()[:8], 16)
    rnd = random.Random(seed)
    distance = 0
    max_iters = 0
    while distance <2 and max_iters < 100:
        # regenerate colors until we get a distinct-ish one
        hue = rnd.random()
        saturation = rnd.uniform(0.4, 0.9)
        brightness = rnd.uniform(0.6, 0.8)        
        r, g, b = colorsys.hsv_to_rgb(hue, saturation, brightness)
        if len(TAG_COLORS) == 0:
            distance = 3
        else:
            # compute min distance to all of a TAG_COLORS
            distance = min([abs(r - r2) + abs(g - g2) + abs(b - b2) for r2, g2, b2 in TAG_COLORS])
        max_iters += 1

    TAG_COLORS.append((r,g,b))    
    return f'#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}'

class KeyLabel(Label):
    def on_key(self, event) -> None:
        self.text = event.key


class TagDir(App):
    """A Textual application that displays a list of files in the current directory,
    and allows you to move files to specified paths with a single keypress.
    """


    CSS_PATH = "tagdir.css"
    BINDINGS = [("escape", "quit", "Quit"), ("insert", "newtag", "Add/modify/delete tag"),
                ("ctrl+z", "undo", "Undo last move"),
                ("ctrl+y", "redo", "Redo last undo"),
                ("tab", "filter", "Set current filter"),]

    def read_tags(self) -> dict:
        """Read the tags file."""
        try:
            with open(self.base_path / "tags.json", "r") as f:
                tags = json.load(f)
        except FileNotFoundError:
            tags = {}
        return tags

    def write_tags(self):
        """Write the tags file."""
        with open(self.base_path / "tags.json", "w") as f:
            json.dump(self.tags, f)

    def init(self):
        """Initialize the application."""
        self.base_path = Path.cwd() if len(sys.argv) == 1 else Path(sys.argv[1])        
        self.tags = self.read_tags()        
        self.history = []
        self.redo_history = []
        self.file_cache = reactive([])
        self.glob_filter = "*"

    def file_filter(self, name):
        """Filter out files that we don't want to show."""
        if name=="tags.json":
            return False
        return pathlib.PurePath(name).match(self.glob_filter)
        

    def init_paths(self):
        """Initialize the paths."""
        self.file_label.update(f"Files ({self.glob_filter})")
        self.files = [p for p in Path.glob(self.base_path, "*") if p.is_file() and self.file_filter(p.name)]   
        self.file_names = [f.name for f in self.files]
        self.file_cache = [ListItem(Label(f.name)) for f in self.files]
        self.file_list.clear()
        for item in self.file_cache:
            self.file_list.append(item)        

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
        self.file_label = Label("Files", classes="section-label")
        
        self.action_label = Label("---", classes="action-label")
        yield self.action_label
        
        self.file_list = ListView(classes='file-list')
        
        self.taglist = ListView(classes='tag-list')
        self.taglist.can_focus = False 
        self.update_tags()
        self.history_widget = History(classes="history-list")
        self.file_list = ListView()
        self.init_paths()
        yield Horizontal(Vertical(Vertical(self.file_label, self.file_list, classes="box"),  classes="column"),
                         Vertical(Vertical(Label("Tags", classes="section-label"), self.taglist, classes="box"),
                                  Vertical(Label("History", classes="section-label"), self.history_widget, classes="box"),  classes="column"), classes="main")
        yield Footer()
        

    def update_tags(self):
        self.taglist.clear()
        for tag in self.tags:
            self.taglist.append(self.make_tag_label(tag))
        self.write_tags()

    def on_key(self, event):
        if self.key_mode=="none":
            # look for a key mapped to a tag
            for tag in self.tags:           
                    if event.key == tag:
                        file = self.files[self.file_list.index]                                  
                        self.move_file(tag, file)

        if event.key == "escape":
            if self.key_mode == "newtag" or self.key_mode=="filter":
                if self.key_mode=="newtag":
                    self.key_input.remove()
                if self.key_mode=="filter":
                    self.filter_box.remove()
                self.key_mode = "none"
                self.update_status("Aborted")
                event.prevent_default()
        else:
            # we are adding a newtag
            if self.key_mode=="newtag":
                # this becomes the new hotkey
                k = str(event.key)                    
                self.keyname.update(k)
                self.keyname.text = k                 
                if k in self.tags:
                    self.tagname.value = self.tags[k]
                self.tagname.focus()
                # and now enable keys to go to the text box
                self.key_mode = "newtag2"
                event.prevent_default()

    
                    
    def on_input_submitted(self, message):                
        def tag_text(tag_key):
            c = get_tag_colors(tag_key)
            return f"[{c}][bold]({tag_key})[/bold] {tag_path}[/{c}]"
        # re-enable hotkeys
        
        if self.key_mode == "newtag2":
            tag_key = self.keyname.text  
            tag_path = self.tagname.value  
            get_tag_colors(tag_key)
            # blank path deletes the tag
            if tag_path=="":            
                self.update_status(f"Deleted tag: {tag_text(tag_key)}", type="warning")
                del self.tags[tag_key]
            else:
                # otherwise, add or update the tag            
                if tag_key in self.tags:                
                    self.update_status(f"Updated tag: {tag_text(tag_key)}", type="info")
                else:
                    self.update_status(f"Added tag: {tag_text(tag_key)}", type="info")                
                self.tags[tag_key] = tag_path     
            self.update_tags()
            # remove the input box
            self.key_input.remove()
        if self.key_mode == "filter":
            self.glob_filter = self.filter_input.value
            self.init_paths()
            self.update_status(f"Filter: {self.glob_filter}", type="info")
            self.filter_box.remove()
        self.key_mode = "none"   
        self.file_list.focus()

    def move(self, file, dest):
        """Actually move the file from file to dest."""
        try:
            os.rename(self.base_path / Path(file), self.base_path / Path(dest))
        except OSError:
            self.update_status(f"Error moving file: {file.name} to {dest}", type="error")
            return False        
        self.file_list.focus()
        return True

    def move_file(self, tag, file):
        """Move the file to the destination given the tag, the file and the destination directory."""
        dest = self.tags[tag]
        # make sure the destination exists
        if not (Path(self.base_path) / Path(dest)).exists():
            (Path(self.base_path) / Path(dest)).mkdir(parents=True, exist_ok=True)            
        success = self.move(file, Path(dest) / Path(file.name))
        if success:
            # update the display and the caches            
            ix = self.file_names.index(file.name)
            elt = self.file_cache[ix]
            elt.remove()
            self.file_cache.pop(ix)
            self.file_names.pop(ix)
            self.files.pop(ix)
            # add it to the history for undo
            self.history.append([tag, file, dest])
            self.history_widget.set_history(self.history)
            self.file_list.index = ix
            # highlight the right file
            self.file_list.post_message_no_wait(ListView.Highlighted(self.file_list, ix))
            # update the status
            c = get_tag_colors(tag)
            self.update_status(f"([bold][{c}]{tag}[/{c}][/bold]) {file} -> [{c}]{self.tags[tag]}[/{c}]", type="success")      
        else:
            self.update_status(f"Error moving file: {file.name} to {self.tags[tag]}", type="error")
        
        
    def on_mount(self):
        # start with the files focused!
        self.file_list.focus()

    def action_quit(self) -> None:
        exit(0)

    def update_status(self, status, type="info"):
        # flash the status bar white, then back to the default after 200ms
        if type=="info":
            status = status 
        elif type=="error":
            status = f"[red]{status}[/red]"
        elif type=="warning":
            status = f"[yellow]{status}[/yellow]"
        elif type=="success":
            status = f"[green]{status}[/green]"
        self.action_label.update(status)
        self.action_label.styles.background = "white"
        self.action_label.styles.animate("background", value=self.action_label._css_styles.background, duration=0.2)

    def action_undo(self) -> None:
        """Undo the last move in the history."""
        if len(self.history)>0:
            last = self.history[-1]
            success = self.move(Path(last[2]) / Path(last[1].name), Path(last[1]))            
            if success:                
                self.history.pop()
                self.redo_history.append(last)   
                self.history_widget.set_history(self.history)   
                self.file_list.focus()      
                self.update_status(f"Undo: {last[1]} <- {last[2]}", type="success")
            else:
                self.update_status(f"Error undoing move: {last[1]} <- {last[2]}", type="error")

        else:
            self.update_status("No more history to undo.", type="warning")

    def action_redo(self):
        if len(self.redo_history)>0:
            last = self.redo_history[-1]
            success = self.move(Path(last[1]), Path(last[2]) / Path(last[1].name))            
            if success:
                
                self.redo_history.pop()
                self.history.append(last)            
                self.history_widget.set_history(self.history)
                self.file_list.focus()
                self.update_status(f"Redo: {last[1]} -> {last[2]}", type="success")
            else:
                self.update_status(f"Error redoing move: {last[1]} -> {last[2]}", type="error")
        else:
            self.update_status("No more history to redo.", type="warning")

    def action_filter(self) -> None:        
        if self.key_mode == "none":
            self.key_mode = "filter"
            self.filter_name = Label("File filter?", id="filtername", classes="filtername")
            self.filter_input = Input(id="filter", placeholder="", classes="filter")
            self.filter_box = Horizontal(self.filter_name, self.filter_input, classes="topbox")
            self.mount(self.filter_box, before=self.action_label)
            self.filter_input.text = self.glob_filter
            self.filter_input.focus()

    def action_newtag(self) -> None:    
        if self.key_mode=="none":
            self.key_mode = "newtag"        
            self.tagname = Input(id="tagname", placeholder="[tag name]", classes="tagname")
            self.keyname = Label("Key?", id="keyname", classes="keyname")
            self.key_input = Horizontal(self.keyname, self.tagname, classes="topbox")
            self.mount(self.key_input, before=self.action_label)
            self.keyname.focus()


def launch_tagdir():
    """Launch the app."""
    t = TagDir()
    t.run()


if __name__ == "__main__":
    launch_tagdir()
