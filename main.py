from nicegui import ui, events
from astropy.coordinates import SkyCoord
from astropy import units as u
import plotly.graph_objects as go

#default value 

#region button controls
control_buttons: dict[str,ui.button] ={}
constellation_buttons: list[ui.button] = []

#Toggle constellation button group depending on which control button was clicked
def toggle_constellationButtons(state: bool) -> None:
    for b in constellation_buttons:
        (b.enable if state else b.disable)()


# Track which control button is active
active_control: str = 'starSelectBtn'

#Change the color of the currently-selected control button
def recolor(active_key: str) -> None:
    global active_control
    active_control = active_key
    for key,b in control_buttons.items():
        b.props(f'color={"negative" if key == active_key else "primary"}').update()

#callbacksdef
def choose_star():
    toggle_constellationButtons(False); recolor('starSelectBtn')
    clear_line_highlight()                      # ← hide any selected line
    plot.update(); _apply_plotly_config()

def choose_line():
    toggle_constellationButtons(False); recolor('lineSelectBtn')
    clear_star_highlight()                      # ← hide star selection
    plot.update(); _apply_plotly_config()

def choose_constellation():
    toggle_constellationButtons(True); recolor('constellationSelectBtn')
    # optional: clear both highlights on entering constellation mode
    clear_star_highlight(); clear_line_highlight()
    plot.update(); _apply_plotly_config()

#endregion

#sign up dialog
with ui.dialog() as signupDialog,ui.card():
    with ui.row():
        ui.label('Username:').style('flex: 1;')
        ui.input().style('flex: 2;')
    with ui.row():
        ui.label('Password:').style('flex: 1;')
        ui.input(password=True).style('flex: 2;')
    with ui.row():
        ui.label('Confirm Password:').style('flex: 1;')
        ui.input(password=True).style('flex: 2;')
    with ui.row():
        ui.button('Sign up', on_click=lambda: (signupDialog.close(), loginDialog.close())).style('flex: 1;') #TODO: don't just close the dialog here
        ui.button('Cancel', on_click=signupDialog.close).style('flex: 1;')

#login dialog
with ui.dialog() as loginDialog,ui.card():
    with ui.row():
        ui.label('Username:').style('flex: 1;')
        ui.input().style('flex: 2;')
    with ui.row():
        ui.label('Password:').style('flex: 1;')
        ui.input(password=True).style('flex: 2;')
    with ui.row():
        ui.button('Login', on_click=loginDialog.close).style('flex: 1;') #TODO: don't just close the dialog here
        ui.button('Sign up', on_click=signupDialog.open).style('flex: 1;')
        ui.button('Cancel', on_click=loginDialog.close).style('flex: 1;')

#share dialog
with ui.dialog() as shareDialog,ui.card():
    with ui.row():
        ui.label('Share selected constellation with user:').style('flex: 1;')
        ui.input('User ID').style('flex: 2;')
    with ui.row():
        ui.button('Share', on_click=shareDialog.close).style('flex: 1;') #TODO: don't just close the dialog here
        ui.button('Cancel', on_click=shareDialog.close).style('flex: 1;')

#'Header' label
with ui.row():
    ui.label('A Sky Full of Stars by Mythic Sky Mapper').style('font-size: 24px; font-weight: bold')

#region Control buttons/slider
class NumStars:
    def __init__(self):
        self.numStars = 5
num_stars_instance = NumStars()
with ui.row().classes('items-center w-full'):
    numStarsSlider = ui.slider(min=0, max=100, step=10).bind_value(num_stars_instance,'numStars').style('width: 200px')

    starSelectBtn = ui.button(icon='star',on_click=choose_star,color='primary').tooltip('Select stars, right-click to unselect')
    lineSelectBtn = ui.button(icon='line_start',on_click=choose_line,color='primary').tooltip('Select links, right-click to delete')
    constellationSelectBtn = ui.button(icon='timeline',on_click=choose_constellation,color='primary').tooltip('Select constellations')
# Register control buttons
    control_buttons.update({
        'starSelectBtn': starSelectBtn,
        'lineSelectBtn': lineSelectBtn,
        'constellationSelectBtn': constellationSelectBtn
    })
    # Set starSelectBtn as visually selected by default
    starSelectBtn.props('color=negative').update()

    with ui.button_group():
        constellationSaveBtn = ui.button(icon='save').tooltip('Save constellation')
        constellationEditBtn = ui.button(icon='edit').tooltip('Edit constellation')
        constellationDeleteBtn = ui.button(icon='delete').tooltip('Delete constellation')
        constellationShareBtn = ui.button(icon='share', on_click=shareDialog.open).tooltip('Share constellation')
        constellation_buttons.extend([constellationSaveBtn, constellationEditBtn, constellationDeleteBtn, constellationShareBtn])
        toggle_constellationButtons(False) #disabled by default

    ui.space()
    loginBtn = ui.button('Login', on_click=loginDialog.open).tooltip('Log in to share/save constellations')
#endregion

#region star map
#coordinates TODO: put the real data here
coords = SkyCoord(
    ra=[10.625, 20.0, 30.0, 156.23, 44.12, 278.45, 12.67, 89.34, 201.56, 175.23, 320.11, 60.78, 110.45, 250.67, 5.89, 135.79, 80.12, 210.34, 300.56, 25.67, 190.23, 270.45, 55.12] * u.deg,
    dec=[41.2, 50.0, 60.0, -12.34, 35.67, 78.90, -45.12, 10.23, 55.67, -60.12, 22.45, 70.89, -30.56, 15.34, 48.90, -80.12, 33.45, 5.67, -25.34, 60.12, -10.45, 40.23, -70.56] * u.deg,
    frame='icrs',
)

#Get the coordinates in the format Plotly wants
lon = ((coords.ra.deg + 180) % 360) - 180   # RA → [-180°, +180°]
lat = coords.dec.deg

#plotly figure
fig = go.Figure()

# Make each link FIRST (so it renders underneath later marker traces)
fig.add_trace(go.Scattergeo(
    lon=[], lat=[],
    mode='lines',
    line=dict(color='blue', width=3),
    name='link',
))

# Invisible large hitbox markers to ease clicking (rendered below visible stars)
fig.add_trace(go.Scattergeo(
    lon=lon, lat=lat,
    mode='markers',
    marker=dict(size=22, color='rgba(0,0,0,0)'),
    hoverinfo='skip',
    name='hitbox',
    showlegend=False,
))

# Visible stars (smaller, above hitbox)
fig.add_trace(go.Scattergeo(
    lon=lon, lat=lat,
    mode='markers',
    marker=dict(size=6, color='black'),
    hoverinfo='text',
    text=[f'Star {i}' for i in range(len(lon))],
    name='stars',
))

# Selection highlight (red with light halo) rendered on top
fig.add_trace(go.Scattergeo(
    lon=[], lat=[],
    mode='markers',
    marker=dict(size=18, color='red', line=dict(color='rgba(255,255,0,0.85)', width=3)),
    name='selection',
    showlegend=False,
))

# Selected line highlight (thick, red) rendered on top
fig.add_trace(go.Scattergeo(
    lon=[], lat=[],
    mode='lines',
    line=dict(color='red', width=5),
    name='link_selected',
    showlegend=False,
))

def _trace_index(name: str) -> int:
    for i, tr in enumerate(fig.data):
        if getattr(tr, 'name', None) == name:
            return i
    raise ValueError(f'Trace with name {name!r} not found')

def clear_star_highlight():
    try:
        si = _trace_index('selection')
        fig.data[si].lon, fig.data[si].lat = [], []
    except ValueError:
        pass

def clear_line_highlight():
    try:
        li = _trace_index('link_selected')
        fig.data[li].lon, fig.data[li].lat = [], []
    except ValueError:
        pass

def _apply_plotly_config():
    # re-apply config after every plot.update() in your setup
    plot._props['options']['config'] = PLOTLY_CONFIG
    plot.update()

# map appearance: frame & 30° grid visible
fig.update_geos(
    projection_type='mollweide',
    showframe=True,
    framecolor='black',
    #Uncomment to show grid lines
    #lonaxis=dict(showgrid=True, dtick=30,
    #             gridcolor='rgba(0,0,0,0.3)', gridwidth=1),
    #lataxis=dict(showgrid=True, dtick=30,
    #             gridcolor='rgba(0,0,0,0.3)', gridwidth=1),
    showland=False, showcountries=False, showcoastlines=False, #this ain't a map of the earth we're looking at
)
plotHeight=750
fig.update_layout(
    #title='Interactive Star Map – pan/zoom disabled', #Change if you think we need a title on the graph
    dragmode=False,        # Don't allow drag‑pan or box zoom
    margin=dict(l=0, r=0, t=40, b=0),
    height=plotHeight,
)

PLOTLY_CONFIG = {
    'scrollZoom': False,          # block wheel zoom
    'doubleClick': False,         # block double‑click autoscale/zoom
    'displayModeBar': False,      # hide toolbar completely
}
#Add to the UI
plot = ui.plotly(fig).style('width: 100%; height: ' + str(plotHeight + 10) + 'px;')
plot._props.setdefault('options', {})['config'] = PLOTLY_CONFIG
plot.update()                                 # push initial options
#endregion

#region click interaction
selected: list[int] = []              # current (partial) pair, 0–2 indices
edges_lon: list[float|None] = []      # accumulated line segment longitudes (with None separators)
edges_lat: list[float|None] = []      # accumulated line segment latitudes
edges_set: set[tuple[int,int]] = set()  # store unique undirected edges (i<j)
selected_edge: tuple[int, int] | None = None  # For line deletion
edges_list: list[tuple[int, int]] = []   # keeps (a,b) in the SAME order as edges_lon/lat

def _trace_index(name: str) -> int:
    for i, tr in enumerate(fig.data):
        if getattr(tr, 'name', None) == name:
            return i
    raise ValueError(f'Trace with name {name!r} not found')

def handle_click(e: events.GenericEventArguments):
    global selected_edge
    stars_idx = _trace_index('stars')
    hitbox_idx = _trace_index('hitbox')
    selection_idx = _trace_index('selection')
    link_idx = _trace_index('link')

    # Line deletion mode
    if active_control == 'lineSelectBtn':
        points = e.args.get('points') or []
        if not points:
            return
        p0 = points[0]
        curve_number = p0.get('curveNumber')
        # Only respond to clicks on the link trace
        if curve_number != link_idx:
            return
        # Find which edge was clicked
        idx = p0.get('pointIndex')
        # Each edge is 2 points, separated by None; so idx//3 gives the edge index
        edge_num = idx // 3
        # Find the edge in edges_lon/edges_lat
        edge_list = list(edges_set)
        if 0 <= edge_num < len(edge_list):
            selected_edge = edge_list[edge_num]
            # Highlight the selected edge (change its color)
            # For simplicity, just notify for now
            ui.notify(f'Edge {selected_edge} selected. Press Del to delete.', type='info', position='top')
        return

    # Only allow selection if starSelectBtn is active
    if active_control == 'starSelectBtn':
        points = e.args.get('points') or []
        if not points:
            return
        p0 = points[0]
        # Resolve current trace indices dynamically (robust against future reordering)
        stars_idx = _trace_index('stars')
        hitbox_idx = _trace_index('hitbox')
        selection_idx = _trace_index('selection')
        link_idx = _trace_index('link')

        # Ensure click came from the stars or hitbox trace
        curve_number = p0.get('curveNumber')
        if curve_number not in (stars_idx, hitbox_idx):
            return  # ignore clicks on selection markers or existing lines
        idx = p0.get('pointIndex')
        if idx is None: #or not (0 <= idx < len(lon)):
            return

        # Toggle deselect if clicking the same single-selected star
        if len(selected) == 1 and selected[0] == idx:
            selected.clear()
            fig.data[selection_idx].lon = []
            fig.data[selection_idx].lat = []
            plot.update(); plot._props['options']['config'] = PLOTLY_CONFIG; plot.update()
            return

        # Add star to selection if not already present (avoid duplicates)
        if idx not in selected:
            selected.append(idx)

        # Keep only first two (ignore any accidental extras robustly)
        if len(selected) > 2:
            selected[:] = selected[:2]

        # Update selection preview (red markers)
        # Filter any accidental out-of-range indices defensively
        valid_indices = [i for i in selected if 0 <= i < len(lon)]
        fig.data[selection_idx].lon = [lon[i] for i in valid_indices]
        fig.data[selection_idx].lat = [lat[i] for i in valid_indices]

        if len(selected) == 2:
            i, j = selected
            # Prevent self-link or duplicate undirected link
            if i == j:
                ui.notify('Cannot link a star to itself', type='warning', position='top')
            else:
                a, b = (i, j) if i < j else (j, i)
                if (a, b) in edges_set:
                    ui.notify('Edge already exists', type='warning', position='top')
                else:
                    edges_set.add((a, b))
                    edges_list.append((a, b))
                    edges_lon.extend([lon[i], lon[j], None])
                    edges_lat.extend([lat[i], lat[j], None])
                    fig.data[link_idx].lon = edges_lon
                    fig.data[link_idx].lat = edges_lat
            # Reset after committing
            selected.clear()
        fig.data[selection_idx].lon = []
        fig.data[selection_idx].lat = []

        plot.update()
        plot._props['options']['config'] = PLOTLY_CONFIG
        plot.update()
    
plot.on('plotly_click', handle_click)           # hook JS → Python

# Listen for Del key to delete selected edge
def _is_delete_key(e: events.KeyEventArguments) -> bool:
    k = getattr(e, 'key', None)
    if isinstance(k, str):                      # older NiceGUI: key is a plain str
        name, code = k, ''
    else:                                       # newer: key is an object with .name/.code
        name = (getattr(k, 'name', '') or '')
        code = (getattr(k, 'code', '') or '')
    return name.lower() in ('delete', 'del') or code == 'Delete'

def _delete_selected_edge():
    global selected_edge, edges_lon, edges_lat, edges_set, edges_list
    if active_control == 'lineSelectBtn' and selected_edge is not None:
        if selected_edge in edges_set:
            edges_set.remove(selected_edge)
        if selected_edge in edges_list:
            edges_list.remove(selected_edge)

        # rebuild link coords from the ordered list
        edges_lon, edges_lat = [], []
        for (i, j) in edges_list:
            edges_lon.extend([lon[i], lon[j], None])
            edges_lat.extend([lat[i], lat[j], None])

        link_idx     = _trace_index('link')
        link_sel_idx = _trace_index('link_selected')

        fig.data[link_idx].lon = edges_lon
        fig.data[link_idx].lat = edges_lat

        # clear red highlight
        fig.data[link_sel_idx].lon = []
        fig.data[link_sel_idx].lat = []
        selected_edge = None

        plot.update(); _apply_plotly_config()
        ui.notify('Edge deleted.', type='info', position='top')

def _on_key(e: events.KeyEventArguments):
    if getattr(e.action, 'keydown', False) and _is_delete_key(e):
        _delete_selected_edge()

# Create the global keyboard listener
ui.keyboard(on_key=_on_key)
#endregion

# Start the UI
ui.run()