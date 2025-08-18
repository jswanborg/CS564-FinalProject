from nicegui import ui, events
from astropy.coordinates import SkyCoord
from astropy import units as u
import plotly.graph_objects as go
import numpy as np
import mysql.connector
import pandas as pd


# Database connection details
DB_CONFIG = {
    'host': 'vm-jgaier',
    'user': 'andrew',
    'password': 'andrew',
    'database': 'mystic_sky_mapper'
}

try:
    # Establish a connection to the MySQL database
    mydb = mysql.connector.connect(**DB_CONFIG)
    cursor = mydb.cursor()
    saved_constellations = []
    logged_in_user = None  # Declare as global so you can modify it

    # Call the stored procedure with a parameter (e.g., limit = 100)
    cursor.callproc('getStars', (500,))
    for result in cursor.stored_results():
        df = pd.DataFrame(result.fetchall(), columns=[desc[0] for desc in result.description])

    #star data object; just load in arbitrarily for now
    star_data = [
        {
            'id': row['SSDS_Object_ID'],
            'ra': row['Right_Ascension'],
            'dec': row['Declination']
        }
        for _, row in df.iterrows()
    ]

    #region button controls
    control_buttons: dict[str,ui.button] ={}
    constellation_buttons: list[ui.button] = []

    #Toggle constellation button group depending on which control button was clicked
    def toggle_constellationButtons(state: bool) -> None:
        for b in constellation_buttons:
            (b.enable if state else b.disable)()


    #Track which control button is active
    #Default to selecting stars
    active_control: str = 'starSelectBtn'

    #Change the color of the currently-selected control button
    def recolor(active_key: str) -> None:
        global active_control
        active_control = active_key
        for key,b in control_buttons.items():
            b.props(f'color={"negative" if key == active_key else "primary"}').update()


    #When we're in our respective modes, make the other hitboxes too small to hit
    def _set_mode_star():
        fig.data[_trace_index('hitbox')].marker.size = 22
        fig.data[_trace_index('link_hit')].marker.size = 0
        _apply_to_plot()

    def _set_mode_link():
        fig.data[_trace_index('hitbox')].marker.size = 0
        fig.data[_trace_index('link_hit')].marker.size = 36
        _apply_to_plot()


    #callbacks; makes it easier to do multiple things when a button is selected
    def choose_star():
        toggle_constellationButtons(False); recolor('starSelectBtn')
        clear_link_highlight(); clear_constellation_highlight()
        _set_mode_star()

    def choose_link():
        toggle_constellationButtons(False); recolor('linkSelectBtn')
        clear_star_highlight(); clear_constellation_highlight()
        _set_mode_link()

    def choose_constellation():
        toggle_constellationButtons(True); recolor('constellationSelectBtn')
        clear_star_highlight(); clear_link_highlight()
        _set_mode_link()  # enable link hit markers for picking
        # Only highlight links that are NOT part of any saved constellation
        used_links = set()
        for c in saved_constellations:
            used_links.update(c['links'])
        unused_links = [e for e in links_list if e not in used_links]
        if unused_links:
            _draw_links_into_trace(unused_links, 'constellation_selected')
        else:
            clear_constellation_highlight()
        _apply_to_plot()
    #endregion

    #sign up dialog
    with ui.dialog() as signupDialog, ui.card():
        with ui.row():
            ui.label('Username:').style('flex: 1;')
            username_input = ui.input().style('flex: 2;')
        with ui.row():
            ui.label('Password:').style('flex: 1;')
            password_input = ui.input(password=True).style('flex: 2;')
        with ui.row():
            ui.label('Confirm Password:').style('flex: 1;')
            confirm_password_input = ui.input(password=True).style('flex: 2;')
        with ui.row():
            def handle_signup():
                username = username_input.value
                password = password_input.value
                confirm_password = confirm_password_input.value
                if not username or not password:
                    ui.notify('Username and password required.', type='negative')
                    return
                if password != confirm_password:
                    ui.notify('Passwords do not match.', type='negative')
                    return
                try:
                    # Check if username is already used
                    cursor.callproc('userNameUsed', (username,))
                    for result in cursor.stored_results():
                        row = result.fetchone()
                    # The second argument is the OUT parameter (1 if used, 0 otherwise)
                    if row[0] == 1:
                        ui.notify('Username is not unique.', type='negative')
                        return
                    # Username is not used, proceed to create user
                    cursor.callproc('createUser', (username, password,))
                    mydb.commit()
                    ui.notify('Sign up successful!', type='positive')
                    signupDialog.close()
                    # Only close loginDialog if it exists
                    if 'loginDialog' in globals():
                        loginDialog.close()
                except Exception as e:
                    ui.notify(f'Error: {e}', type='negative')
            ui.button('Sign up', on_click=handle_signup).style('flex: 1;')
            ui.button('Cancel', on_click=signupDialog.close).style('flex: 1;')

    #login dialog
    with ui.dialog() as loginDialog, ui.card():
        with ui.row():
            ui.label('Username:').style('flex: 1;')
            login_username_input = ui.input().style('flex: 2;')
        with ui.row():
            ui.label('Password:').style('flex: 1;')
            login_password_input = ui.input(password=True).style('flex: 2;')
        with ui.row():
            def handle_login():
                global logged_in_user
                username = login_username_input.value
                password = login_password_input.value
                if not username or not password:
                    ui.notify('Username and password required.', type='negative')
                    return
                try:
                    # Call checkPassword stored procedure
                    cursor.callproc('checkPassword', (username, password,))
                    for result in cursor.stored_results():
                        row = result.fetchone()
                    print("Username:", username)
                    print("Password:", password)
                    print("Result args:", row[0])
                    if row[0] == 1:
                        logged_in_user = username  # Save the username to the global
                        ui.notify('Login successful!', type='positive')
                        loginDialog.close()
                    else:
                        ui.notify('Incorrect username or password.', type='negative')
                except Exception as e:
                    ui.notify(f'Error: {e}', type='negative')
            ui.button('Login', on_click=handle_login).style('flex: 1;')
            ui.button('Sign up', on_click=signupDialog.open).style('flex: 1;')
            ui.button('Cancel', on_click=loginDialog.close).style('flex: 1;')

    #share dialog
    with ui.dialog() as shareDialog, ui.card():
        with ui.row():
            ui.label('Share selected constellation with user:').style('flex: 1;')
            ui.input('User ID').style('flex: 2;')
        with ui.row():
            ui.button('Share', on_click=shareDialog.close).style('flex: 1;') #TODO: don't just close the dialog here
            ui.button('Cancel', on_click=shareDialog.close).style('flex: 1;')

    #'Header' label
    with ui.row():
        ui.label('A Sky Full of Stars by Mythic Sky Mapper').style('font-size: 24px; font-weight: bold')

    #region buttons/slider
    class NumStars:
        def __init__(self):
            self.numStars = 5
    num_stars_instance = NumStars()
    with ui.row().classes('items-center w-full'):
        #numStarsSlider = ui.slider(min=0, max=100, step=10).bind_value(num_stars_instance,'numStars').style('width: 200px')

        starSelectBtn = ui.button(icon='star',on_click=choose_star,color='primary').tooltip('Select stars, select the same star again to unselect')
        linkSelectBtn = ui.button(icon='link',on_click=choose_link,color='primary').tooltip('Select links, use Del key to delete')
        constellationSelectBtn = ui.button(icon='timeline',on_click=choose_constellation,color='primary').tooltip('Select constellations')
        
        # Register control buttons
        control_buttons.update({
            'starSelectBtn': starSelectBtn,
            'linkSelectBtn': linkSelectBtn,
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


    #TODO: comment this better
    def save_constellation():
        
        # Get selected links from the overlay trace
        ci = _trace_index('constellation_selected')
        # Find which links are currently highlighted
        # We'll use the links that were last drawn into the overlay
        # (Assume _draw_links_into_trace was called with the current selection)
        # For simplicity, store the currently highlighted links
        highlighted_links = []
        # Reconstruct from the overlay trace (lon/lat) by matching to links_list
        # But we already have the last selection in the overlay, so let's keep a global
        global last_constellation_links,logged_in_user
        try:
            links_to_save = last_constellation_links if last_constellation_links else []
        except NameError:
            links_to_save = []
        
        if not logged_in_user:  # Check if user is logged in
            ui.notify('Please log in to save constellations.', type='negative')
            return
        constellation_name = constellationNameInput.value
        print(logged_in_user)
        cursor.callproc('createConstellation', (constellation_name,logged_in_user,))
        for result in cursor.stored_results():
                        row = result.fetchone()
        constellation_ID = row[0]  # Get the ID of the newly created constellation
        saved_constellations.append({'id': constellation_ID, 'name': constellation_name, 'links': links_to_save})
        for link in links_to_save:
            print(constellation_ID, link[0], link[1])
            cursor.callproc('addLine', (constellation_ID, link[0], link[1],))
        mydb.commit()  # Commit after adding all lines
        ui.notify('Saved!', type='positive', position='top')
        clear_constellation_highlight()
        _apply_to_plot()

        

    constellationSaveBtn.on('click', save_constellation)


    #Region name of constellation controls
    with ui.row().classes('items-center'):
        ui.label('Constellation name:').style('margin-right: 8px;')
        constellationNameInput = ui.input().style('min-width: 180px;')
        constellationNameInput.disable()

    # Enable/disable constellationNameInput based on active_control
    def update_constellation_name_input():
        if active_control == 'constellationSelectBtn':
            constellationNameInput.enable()
        else:
            constellationNameInput.disable()

    # Patch recolor to also update input enabled state
    _orig_recolor = recolor
    def recolor(active_key: str) -> None:
        _orig_recolor(active_key)
        update_constellation_name_input()
    #endregion

    #region star map
    #coordinates TODO: put the real data here
    coords = SkyCoord(
        ra=[s['ra'] for s in star_data] * u.deg,
        dec=[s['dec'] for s in star_data] * u.deg,
        frame='icrs',
    )

    #Get the coordinates in the format Plotly wants
    lon = ((coords.ra.deg + 180) % 360) - 180   # RA → [-180°, +180°]
    lat = coords.dec.deg


    #plotly figure
    fig = go.Figure()
    fig.update_layout(clickmode='event')


    #Traces that make parts of the plot visible and/or selectable
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
        text=[f"Star {s['id']}: RA={s['ra']}, Dec={s['dec']}" for s in star_data],
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

    # Selected link highlight
    fig.add_trace(go.Scattergeo(
        lon=[], lat=[],
        mode='lines',
        line=dict(color='red', width=5),
        name='link_selected',
        showlegend=False,
    ))

    # Selected constellation highlight (group of links)
    fig.add_trace(go.Scattergeo(
        lon=[], lat=[],
        mode='lines',
        line=dict(color='orange', width=6),
        name='constellation_selected',
        showlegend=False,
    ))

    # One invisible marker per curve position to make links clickable
    fig.add_trace(go.Scattergeo(
        lon=[], lat=[],
        mode='markers',
        marker=dict(size=32, color='rgba(0,0,0,0)'),  # 0s => invisible
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

    def clear_link_highlight():
        try:
            li = _trace_index('link_selected')
            fig.data[li].lon, fig.data[li].lat = [], []
        except ValueError:
            pass

    def clear_constellation_highlight():
        try:
            ci = _trace_index('constellation_selected')
            fig.data[ci].lon, fig.data[ci].lat = [], []
        except ValueError:
            pass

    #re-apply config and update whenever needed
    #TODO: Legend controls still show up and are usable but *very* broken
    PLOTLY_CONFIG = {
        'scrollZoom': False,          # block wheel zoom
        'doubleClick': False,         # block double‑click autoscale/zoom
        'displayModeBar': False,      # hide toolbar completely
    }

    def _apply_to_plot():
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
        #title='Interactive Star Map – pan/zoom disabled', #Change/uncomment if you think we need a title on the graph
        dragmode=False,        # Don't allow drag‑pan or box zoom
        margin=dict(l=0, r=0, t=40, b=0),
        height=plotHeight,
    )

    #Add to the UI
    plot = ui.plotly(fig).style('width: 100%; height: ' + str(plotHeight + 10) + 'px;')
    plot._props.setdefault('options', {})['config'] = PLOTLY_CONFIG
    plot.update()                                 # push initial options
    #endregion

    #region click interaction
    selected: list[int] = []              # current (partial) pair, 0–2 indices
    links_lon: list[float|None] = []      # accumulated link segment longitudes (with None separators)
    links_lat: list[float|None] = []      # accumulated link segment latitudes
    links_set: set[tuple[int,int]] = set()  # store unique undirected links (i<j)
    selected_link: tuple[int, int] | None = None  # For link deletion
    links_list: list[tuple[int, int]] = []   # keeps (a,b) in the SAME order as links_lon/lat
    N_CURVE_SAMPLES = 64      # drawing detail for each link (curvature)
    N_HIT_MARKERS   = 9       # click targets per link along the curve

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

    def _rebuild_links_from_list():
        global links_lon, links_lat
        links_lon, links_lat = [], []

        hit_lon, hit_lat, hit_link = [], [], []
        for e_idx, (i, j) in enumerate(links_list):
            # visible curved blue path (+ None separator)
            LON, LAT = _gc_path_lons_lats(i, j, N_CURVE_SAMPLES)
            links_lon.extend(LON + [None]); links_lat.extend(LAT + [None])

            # many invisible click targets along the curve (skip exact endpoints)
            c1, c2 = coords[i], coords[j]
            sep = c1.separation(c2); pa = c1.position_angle(c2)
            for f in np.linspace(0.1, 0.9, N_HIT_MARKERS):
                p = c1.directional_offset_by(pa, sep * f)
                hit_lon.append(_wrap180(p.ra.deg))
                hit_lat.append(p.dec.deg)
                hit_link.append(e_idx)          # ← maps marker → link index

        link_idx     = _trace_index('link')
        link_hit_idx = _trace_index('link_hit')

        fig.data[link_idx].lon,     fig.data[link_idx].lat     = links_lon, links_lat
        fig.data[link_hit_idx].lon, fig.data[link_hit_idx].lat = hit_lon,   hit_lat
        fig.data[link_hit_idx].customdata = hit_link           # ← crucial

    def _draw_links_into_trace(links: list[tuple[int,int]], trace_name: str):
        """Render the given links as curved segments into the named trace."""
        global last_constellation_links
        if trace_name == 'constellation_selected':
            last_constellation_links = links.copy()
        LON_ALL: list[float|None] = []
        LAT_ALL: list[float|None] = []
        for i, j in links:
            LON, LAT = _gc_path_lons_lats(i, j, N_CURVE_SAMPLES)
            LON_ALL.extend(LON + [None])
            LAT_ALL.extend(LAT + [None])
        ti = _trace_index(trace_name)
        fig.data[ti].lon, fig.data[ti].lat = LON_ALL, LAT_ALL

    def _build_constellation_from_link(link: tuple[int,int]) -> list[tuple[int,int]]:
        """Return all links connected to the given link as a constellation (connected component)."""
        if not links_list:
            return []
        # Build adjacency of stars
        adj: dict[int, set[int]] = {}
        for a, b in links_list:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        # BFS/DFS from the two endpoints
        start_a, start_b = link
        stack = [start_a, start_b]
        seen: set[int] = set()
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            for m in adj.get(n, ()): stack.append(m)
        # Collect all links whose endpoints are within seen
        comp_links = [(a, b) for (a, b) in links_list if a in seen and b in seen]
        return comp_links

    def _highlight_all_links_as_constellation():
        if links_list:
            _draw_links_into_trace(links_list, 'constellation_selected')
        else:
            clear_constellation_highlight()
        _apply_to_plot()

    def handle_click(e: events.GenericEventArguments):
        global selected_link, selected

        stars_idx      = _trace_index('stars')
        hitbox_idx     = _trace_index('hitbox')
        link_hit_idx   = _trace_index('link_hit')
        selection_idx  = _trace_index('selection')

        pts = e.args.get('points') or []
        if not pts:
            return

        # ================= CONSTELLATION MODE =================
        if active_control == 'constellationSelectBtn':
            link_hit_idx = _trace_index('link_hit')
            p = next((x for x in pts if x.get('curveNumber') == link_hit_idx), None)
            if not p:
                return
            idx = p.get('pointIndex', p.get('pointNumber'))
            if idx is None:
                return
            link_num = int(idx) // N_HIT_MARKERS
            if not (0 <= link_num < len(links_list)):
                return
            seed = links_list[link_num]
            comp = _build_constellation_from_link(seed)
            _draw_links_into_trace(comp, 'constellation_selected')
            _apply_to_plot()
            return

        # ================= LINK MODE =================
        if active_control == 'linkSelectBtn':
            pts = e.args.get('points') or []
            link_hit_idx = _trace_index('link_hit')

            # Prefer the hit layer; if the click didn't land on it, ignore
            p = next((x for x in pts if x.get('curveNumber') == link_hit_idx), None)
            if not p:
                return

            # Derive link index from the hit point's index within the link_hit trace
            idx = p.get('pointIndex', p.get('pointNumber'))
            if idx is None:
                return
            link_num = int(idx) // N_HIT_MARKERS
            if not (0 <= link_num < len(links_list)):
                return

            selected_link = links_list[link_num]
            i, j = selected_link

            # Draw a curved red overlay for the selected link
            LON, LAT = _gc_path_lons_lats(i, j, N_CURVE_SAMPLES)
            sel_idx = _trace_index('link_selected')
            fig.data[sel_idx].lon, fig.data[sel_idx].lat = LON, LAT

            _apply_to_plot()
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
                _apply_to_plot()
                return

            if idx not in selected:
                selected.append(idx)
            if len(selected) > 2:
                selected[:] = selected[-2:]  # keep most recent two

            # show big red markers for current selection
            fig.data[selection_idx].lon = [lon[i] for i in selected]
            fig.data[selection_idx].lat = [lat[i] for i in selected]

            # commit link when we have two picks
            if len(selected) == 2:
                i, j = selected
                a, b = (i, j) if i < j else (j, i)
                if a != b and (a, b) not in links_set:
                    links_set.add((a, b))
                    links_list.append((a, b))
                    _rebuild_links_from_list()       # updates blue curve + hit markers

                selected.clear()
                fig.data[selection_idx].lon = []
                fig.data[selection_idx].lat = []

            _apply_to_plot()

    plot.on('plotly_click', handle_click)           # hook JS → Python

    # Listen for Del key to delete selected link
    def _is_delete_key(e: events.KeyEventArguments) -> bool:
        k = getattr(e, 'key', None)
        if isinstance(k, str):                      # older NiceGUI: key is a plain str
            name, code = k, ''
        else:                                       # newer: key is an object with .name/.code
            name = (getattr(k, 'name', '') or '')
            code = (getattr(k, 'code', '') or '')
        return name.lower() in ('delete', 'del') or code == 'Delete'

    def _delete_selected_link():
        global selected_link, links_set, links_list
        if active_control == 'linkSelectBtn' and selected_link is not None:
            if selected_link in links_set:
                links_set.remove(selected_link)
            if selected_link in links_list:
                links_list.remove(selected_link)

            # rebuild both traces from the ordered list
            _rebuild_links_from_list()

            # clear red overlay
            link_sel_idx = _trace_index('link_selected')
            fig.data[link_sel_idx].lon = []
            fig.data[link_sel_idx].lat = []
            selected_link = None

            _apply_to_plot()
            #ui.notify('link deleted.', type='info', position='top')

    def _on_key(e: events.KeyEventArguments):
        if getattr(e.action, 'keydown', False) and _is_delete_key(e):
            _delete_selected_link()

    # Create the global keyboard listener
    ui.keyboard(on_key=_on_key)
    #endregion

    def cleanup():
        if 'cursor' in locals():
            cursor.close()
        if 'mydb' in locals() and mydb.is_connected():
            mydb.close()
            print("MySQL connection closed.")

    #ui.on_disconnect(cleanup)
    # Start the UI
    ui.run()

except mysql.connector.Error as err:
    print(f"Error connecting to MySQL: {err}")

