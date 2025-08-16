from nicegui import ui, events
from astropy.coordinates import SkyCoord
from astropy import units as u
import plotly.graph_objects as go
import numpy as np


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

def _set_mode_star():
    fig.data[_trace_index('hitbox')].marker.size = 22
    fig.data[_trace_index('link_hit')].marker.size = 0
    plot.update(); _apply_plotly_config()

def _set_mode_line():
    fig.data[_trace_index('hitbox')].marker.size = 0
    fig.data[_trace_index('link_hit')].marker.size = 36
    plot.update(); _apply_plotly_config()

#callbacksdef
def choose_star():
    toggle_constellationButtons(False); recolor('starSelectBtn')
    clear_line_highlight()
    _set_mode_star()

def choose_line():
    toggle_constellationButtons(False); recolor('lineSelectBtn')
    clear_star_highlight()
    _set_mode_line()

def choose_constellation():
    toggle_constellationButtons(True); recolor('constellationSelectBtn')
    clear_star_highlight(); clear_line_highlight()
    _set_mode_star()  # or define a separate mode if you prefer

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

    starSelectBtn = ui.button(icon='star',on_click=choose_star,color='primary').tooltip('Select stars, select the same star again to unselect')
    lineSelectBtn = ui.button(icon='line_start',on_click=choose_line,color='primary').tooltip('Select links, use Del key to delete')
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
fig.update_layout(clickmode='event')

# Make each link FIRST (so it renders underneath later marker traces)
fig.add_trace(go.Scattergeo(
    lon=[], lat=[],
    mode='lines',
    line=dict(color='blue', width=3),
    name='link',
))
# Invisible large star hitbox markers to ease clicking
fig.add_trace(go.Scattergeo(
    lon=lon, lat=lat,
    mode='markers',
    marker=dict(size=22, color='rgba(0,0,0,0)'),
    hoverinfo='skip',
    name='hitbox',
    showlegend=False,
))

# Visible stars
fig.add_trace(go.Scattergeo(
    lon=lon, lat=lat,
    mode='markers',
    marker=dict(size=6, color='black'),
    hoverinfo='text',
    text=[f'Star {i}' for i in range(len(lon))],
    name='stars',
))

# Selected star highlight
fig.add_trace(go.Scattergeo(
    lon=[], lat=[],
    mode='markers',
    marker=dict(size=18, color='red', line=dict(color='rgba(255,255,0,0.85)', width=3)),
    name='selection',
    showlegend=False,
))

# Selected line highlight
fig.add_trace(go.Scattergeo(
    lon=[], lat=[],
    mode='lines',
    line=dict(color='red', width=5),
    name='link_selected',
    showlegend=False,
))

# One invisible marker per curve position to make lines clickable
fig.add_trace(go.Scattergeo(
    lon=[], lat=[],
    mode='markers',
    marker=dict(size=32, color='rgba(0,0,0,0.1)'),  # 0s => invisible
    name='link_hit',
    hoverinfo='none',
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
N_CURVE_SAMPLES = 64      # drawing detail for each edge (curvature)
N_HIT_MARKERS   = 9       # click targets per edge along the curve

def _wrap180(x: float) -> float:
    return ((x + 180.0) % 360.0) - 180.0

def _gc_path_lons_lats(i: int, j: int, samples: int = N_CURVE_SAMPLES):
    c1, c2 = coords[i], coords[j]
    sep = c1.separation(c2)
    pa  = c1.position_angle(c2)
    fracs = np.linspace(0.0, 1.0, samples)
    pts = [c1.directional_offset_by(pa, sep * f) for f in fracs]
    lon_deg = [_wrap180(p.ra.deg) for p in pts]
    lat_deg = [p.dec.deg         for p in pts]
    out_lon, out_lat = [lon_deg[0]], [lat_deg[0]]
    for k in range(1, len(lon_deg)):
        if abs(lon_deg[k] - lon_deg[k-1]) > 180 - 1e-6:
            out_lon.append(None); out_lat.append(None)
        out_lon.append(lon_deg[k]); out_lat.append(lat_deg[k])
    return out_lon, out_lat

def _rebuild_edges_from_list():
    global edges_lon, edges_lat
    edges_lon, edges_lat = [], []

    hit_lon, hit_lat, hit_edge = [], [], []
    for e_idx, (i, j) in enumerate(edges_list):
        # visible curved blue path (+ None separator)
        LON, LAT = _gc_path_lons_lats(i, j, N_CURVE_SAMPLES)
        edges_lon.extend(LON + [None]); edges_lat.extend(LAT + [None])

        # many invisible click targets along the curve (skip exact endpoints)
        c1, c2 = coords[i], coords[j]
        sep = c1.separation(c2); pa = c1.position_angle(c2)
        for f in np.linspace(0.1, 0.9, N_HIT_MARKERS):
            p = c1.directional_offset_by(pa, sep * f)
            hit_lon.append(_wrap180(p.ra.deg))
            hit_lat.append(p.dec.deg)
            hit_edge.append(e_idx)          # ← maps marker → edge index

    link_idx     = _trace_index('link')
    link_hit_idx = _trace_index('link_hit')

    fig.data[link_idx].lon,     fig.data[link_idx].lat     = edges_lon, edges_lat
    fig.data[link_hit_idx].lon, fig.data[link_hit_idx].lat = hit_lon,   hit_lat
    fig.data[link_hit_idx].customdata = hit_edge           # ← crucial

def handle_click(e: events.GenericEventArguments):
    global selected_edge, selected

    stars_idx      = _trace_index('stars')
    hitbox_idx     = _trace_index('hitbox')
    link_hit_idx   = _trace_index('link_hit')
    selection_idx  = _trace_index('selection')
    link_sel_idx   = _trace_index('link_selected')

    pts = e.args.get('points') or []
    if not pts:
        return

    # ================= LINE MODE =================
    if active_control == 'lineSelectBtn':
        pts = e.args.get('points') or []
        link_hit_idx = _trace_index('link_hit')

        # Prefer the hit layer; if the click didn't land on it, ignore
        p = next((x for x in pts if x.get('curveNumber') == link_hit_idx), None)
        if not p:
            return

        # Derive edge index from the hit point's index within the link_hit trace
        idx = p.get('pointIndex', p.get('pointNumber'))
        if idx is None:
            return
        edge_num = int(idx) // N_HIT_MARKERS
        ui.notify(f'link_hit picked: idx={idx}, edge_num={edge_num}', position='top') #debug
        if not (0 <= edge_num < len(edges_list)):
            return

        selected_edge = edges_list[edge_num]
        i, j = selected_edge

        # Draw a curved red overlay for the selected edge
        LON, LAT = _gc_path_lons_lats(i, j, N_CURVE_SAMPLES)
        sel_idx = _trace_index('link_selected')
        fig.data[sel_idx].lon, fig.data[sel_idx].lat = LON, LAT

        plot.update(); _apply_plotly_config()
        return
    
    # ================= STAR MODE =================
    if active_control == 'starSelectBtn':
        # pick a star (either visible star or invisible star hitbox)
        p = next((p for p in pts if p.get('curveNumber') in (stars_idx, hitbox_idx)), None)
        if not p:
            return
        idx = p.get('pointIndex', p.get('pointNumber'))
        if idx is None:
            return

        # toggle deselect if re-clicking the same star
        if len(selected) == 1 and selected[0] == idx:
            selected.clear()
            fig.data[selection_idx].lon = []
            fig.data[selection_idx].lat = []
            plot.update(); _apply_plotly_config()
            return

        if idx not in selected:
            selected.append(idx)
        if len(selected) > 2:
            selected[:] = selected[-2:]  # keep most recent two

        # show big red markers for current selection
        fig.data[selection_idx].lon = [lon[i] for i in selected]
        fig.data[selection_idx].lat = [lat[i] for i in selected]

        # commit edge when we have two picks
        if len(selected) == 2:
            i, j = selected
            a, b = (i, j) if i < j else (j, i)
            if a != b and (a, b) not in edges_set:
                edges_set.add((a, b))
                edges_list.append((a, b))
                _rebuild_edges_from_list()       # updates blue curve + hit markers

            selected.clear()
            fig.data[selection_idx].lon = []
            fig.data[selection_idx].lat = []

        plot.update(); _apply_plotly_config()
  
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
    global selected_edge, edges_set, edges_list
    if active_control == 'lineSelectBtn' and selected_edge is not None:
        if selected_edge in edges_set:
            edges_set.remove(selected_edge)
        if selected_edge in edges_list:
            edges_list.remove(selected_edge)

        # rebuild both traces from the ordered list
        _rebuild_edges_from_list()

        # clear red overlay
        link_sel_idx = _trace_index('link_selected')
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