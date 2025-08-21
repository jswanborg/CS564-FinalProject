from nicegui import ui, events
from astropy.coordinates import SkyCoord
from astropy import units as u
import plotly.graph_objects as go
import numpy as np
import mysql.connector
import pandas as pd
import json


#Database connection details; change if needed
DB_CONFIG = {
    'host': 'vm-jgaier',
    'user': 'andrew',
    'password': 'andrew',
    'database': 'mystic_sky_mapper'
}

try:
    #Establish a connection to the MySQL database
    mydb = mysql.connector.connect(**DB_CONFIG)
    cursor = mydb.cursor()
    saved_constellations = []
    logged_in_user = None  #Declare as global so you can modify it

    #Call the stored procedure with a parameter (e.g., limit = 100)
    cursor.callproc('getStars', (500,))
    for result in cursor.stored_results():
        df = pd.DataFrame(result.fetchall(), columns=[desc[0] for desc in result.description])  # type: ignore

    #star data object; just load in arbitrarily for now
    star_data = [
        {
            'id': row['SSDS_Object_ID'],
            'ra': row['Right_Ascension'],
            'dec': row['Declination']
        }
        for _, row in df.iterrows()
    ]

    # Map SSDS object ID -> index in star_data for fast conversion
    star_index_by_id: dict[int, int] = {}
    for idx, s in enumerate(star_data):
        sid_val = s.get('id') if isinstance(s, dict) else None
        if sid_val is None:
            continue
        try:
            sid = int(sid_val)
        except (TypeError, ValueError):
            continue
        star_index_by_id[sid] = idx

    def _id_to_index(sid) -> int | None:
        try:
            return star_index_by_id.get(int(sid))
        except (TypeError, ValueError):
            return None

    def _normalize_pair(i: int, j: int) -> tuple[int, int]:
        return (i, j) if i < j else (j, i)

    def _parse_links_field(links_field) -> list[tuple[int, int]]:
        """Convert a DB-returned links field into index pairs.
        Accepts list/tuple of pairs, JSON string/bytes, or a delimited string.
        Returns unique (i,j) index pairs with i<j. Unknown/invalid pairs are ignored.
        """
        pairs: list[tuple[int, int]] = []
        raw = links_field
        if raw is None:
            return pairs
        # bytes -> str
        if isinstance(raw, (bytes, bytearray, memoryview)):
            try:
                raw = bytes(raw).decode('utf-8')
            except Exception:
                raw = str(bytes(raw))
        # If already a list/tuple-like
        if isinstance(raw, (list, tuple)):
            for item in raw:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    a_i = _id_to_index(item[0])
                    b_i = _id_to_index(item[1])
                    if a_i is not None and b_i is not None and a_i != b_i:
                        pairs.append(_normalize_pair(a_i, b_i))
            # dedupe
            return list({p for p in pairs})
        # Try JSON first if it's a string
        if isinstance(raw, str):
            txt = raw.strip()
            if txt:
                # Try JSON arrays like [[id1,id2],[id3,id4]] or objects
                try:
                    data = json.loads(txt)
                    return _parse_links_field(data)
                except Exception:
                    pass
                # Fallback: parse simple delimiters like "id1,id2;id3,id4" or "id1-id2;id3-id4"
                chunks = [c for c in txt.replace('(', '').replace(')', '').replace('[', '').replace(']', '').split(';') if c]
                if len(chunks) == 1 and ',' not in chunks[0] and '-' not in chunks[0]:
                    # maybe comma-separated pairs separated by spaces
                    chunks = [x for x in txt.split() if x]
                for ch in chunks:
                    if not ch:
                        continue
                    sep = ',' if ',' in ch else ('-' if '-' in ch else None)
                    if not sep:
                        continue
                    parts = [p for p in ch.split(sep) if p]
                    if len(parts) != 2:
                        continue
                    a_i = _id_to_index(parts[0])
                    b_i = _id_to_index(parts[1])
                    if a_i is not None and b_i is not None and a_i != b_i:
                        pairs.append(_normalize_pair(a_i, b_i))
        # dedupe
        return list({p for p in pairs})

    def _pairs_from_row(row) -> list[tuple[int, int]]:
        """Derive link index pairs from a row.
        Supports two shapes:
          - (id, name, links_blob)
          - (id, name, star_id_a, star_id_b) repeated per link
        """
        try:
            if len(row) >= 4 and row[2] is not None and row[3] is not None:
                a_i = _id_to_index(row[2])
                b_i = _id_to_index(row[3])
                if a_i is not None and b_i is not None and a_i != b_i:
                    return [_normalize_pair(a_i, b_i)]
                return []
            if len(row) >= 3:
                return _parse_links_field(row[2])
        except Exception:
            return []
        return []
 
    #region button controls
    control_buttons: dict[str,ui.button] = {}
    constellation_buttons: list[ui.button] = []
    constellation_action_buttons: list[ui.button] = []

    #Toggle constellation button group depending on which control button was clicked
    def _toggle_constellationButtons(state: bool) -> None:
        for b in constellation_buttons:
            (b.enable if state else b.disable)()

    #Utility to enable/disable constellation action buttons
    def _toggle_constellation_action_buttons(enabled: bool):
        for b in constellation_action_buttons:
            (b.enable if enabled else b.disable)()

    #Track which control button is active
    #Default to selecting stars
    active_control: str = 'starSelectBtn'

    #Enable/disable constellationNameInput based on active_control
    def update_constellation_name_input():
        if active_control == 'constellationSelectBtn':
            constellationNameInput.enable()
        else:
            constellationNameInput.disable()
    #endregion

    # Plotly config (constant), used by plot and helpers
    PLOTLY_CONFIG = {
        'scrollZoom': False,
        'doubleClick': False,
        'displayModeBar': False,
    }

    # Define callbacks that will be bound to UI controls later
    def recolor(active_key: str) -> None:
        global active_control
        active_control = active_key
        for key, b in control_buttons.items():
            b.props(f'color={"negative" if key == active_key else "primary"}').update()
        update_constellation_name_input()



    #When we're in our respective modes, make the other star_hites too small to hit
    def _set_mode_star():
        fig.data[_trace_index('star_hit')].marker.size = 22  #type: ignore
        fig.data[_trace_index('link_hit')].marker.size = 0   #type: ignore
        _apply_to_plot()

    def _set_mode_link():
        fig.data[_trace_index('star_hit')].marker.size = 0 #type: ignore
        fig.data[_trace_index('link_hit')].marker.size = 36 #type: ignore
        _apply_to_plot()


    #callbacks; makes it easier to do multiple things when a button is selected
    def choose_star():
        _toggle_constellationButtons(False); recolor('starSelectBtn')
        _clear_link_highlight(); _clear_constellation_highlight()
        _set_mode_star()

    def choose_link():
        _toggle_constellationButtons(False); recolor('linkSelectBtn')
        _clear_star_highlight(); _clear_constellation_highlight()
        _set_mode_link()

    def choose_constellation():
        _toggle_constellationButtons(True); recolor('constellationSelectBtn')
        _clear_star_highlight(); _clear_link_highlight()
        _set_mode_link()  #enable link hit markers for picking
        #Only highlight links that are NOT part of any saved constellation
        used_links = set()
        for c in saved_constellations:
            used_links.update(c['links'])
        unused_links = [e for e in links_list if e not in used_links]
        if unused_links:
            _draw_links_into_trace(unused_links, 'constellation_selected')
            _toggle_constellation_action_buttons(True)
        else:
            _clear_constellation_highlight()
            _toggle_constellation_action_buttons(False)
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
                    #Check if username is already used
                    cursor.callproc('userNameUsed', (username,))
                    for result in cursor.stored_results():
                        row = result.fetchone()
                    #The second argument is the OUT parameter (2 if used, 1 otherwise)
                    if row[0] == 2: #type: ignore
                        ui.notify('Username is not unique.', type='negative')
                        return
                    #Username is not used, proceed to create user
                    cursor.callproc('createUser', (username, password,))
                    mydb.commit()
                    ui.notify('Sign up successful!', type='positive')
                    signupDialog.close()
                    #Only close loginDialog if it exists
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
                    #Call checkPassword stored procedure
                    cursor.callproc('checkPassword', (username, password,))
                    for result in cursor.stored_results():
                        row = result.fetchone()
                    userId = row[0] #type: ignore
                    if userId != 0:
                        logged_in_user = username  #Save the username to the global
                        ui.notify('Login successful!', type='positive')
                        loginDialog.close()

                        # Fetch constellations made by and shared with this user
                        try:
                            constellations = []
                            # Get this user's constellations
                            cursor.callproc('getUserConst', (userId,))
                            for result in cursor.stored_results():
                                rows = result.fetchall()
                                if rows:
                                    constellations.extend(rows)
                            # Get constellations shared with this user
                            cursor.callproc('getConstSharedWitUser', (userId,)) #no t in with
                            for result in cursor.stored_results():
                                rows = result.fetchall()
                                if rows:
                                    constellations.extend(rows)

                            # For each constellation, pull its lines and convert to index pairs
                            for c in constellations:
                                const_id = c[0]
                                const_name = c[1] if len(c) > 1 else str(const_id)
                                # Fetch lines for this constellation
                                cursor.callproc('ConstLines', (const_id,))
                                link_rows = []
                                for r in cursor.stored_results():
                                    fetched = r.fetchall()
                                    if fetched:
                                        link_rows.extend(fetched)
                                # Convert rows to index pairs
                                link_pairs: list[tuple[int,int]] = []
                                for lr in link_rows:
                                    if lr is None:
                                        continue
                                    # Accept shapes like (star_id_a, star_id_b, ...) or dicts
                                    if isinstance(lr, (list, tuple)) and len(lr) >= 2:
                                        a_i = _id_to_index(lr[0])
                                        b_i = _id_to_index(lr[1])
                                    elif isinstance(lr, dict):
                                        a_i = _id_to_index(lr.get('star_a'))
                                        b_i = _id_to_index(lr.get('star_b'))
                                    else:
                                        a_i = b_i = None
                                    if a_i is not None and b_i is not None and a_i != b_i:
                                        link_pairs.append(_normalize_pair(a_i, b_i))
                                # Deduplicate
                                link_pairs = list({p for p in link_pairs})
                                saved_constellations.append({
                                    'id': const_id,
                                    'name': const_name,
                                    'links': link_pairs,
                                })

                            # Update plot with loaded constellations
                            _draw_all_saved_constellations()  # type: ignore
                            _clear_constellation_highlight()  # type: ignore
                            _apply_to_plot()  # type: ignore
                        except Exception as e:
                            ui.notify(f"Failed to get constellations: {e}", type='negative')
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
            shareDialogUserInput = ui.input().style('flex: 2;')
        with ui.row():
            # Share button clicked
            def share_constellation():
                share_user_name = shareDialogUserInput.value
                # Find the currently selected constellation
                try:
                    # Use the last selected constellation if available
                    if saved_constellations:
                        const_ID = saved_constellations[-1]['id']
                    else:
                        ui.notify('No constellation selected to share.', type='negative')
                        return
                    cursor.callproc('share', (const_ID, share_user_name))
                    mydb.commit()
                    ui.notify(f"Constellation shared with {share_user_name}!", type='positive')
                except Exception as e:
                    ui.notify(f"Error sharing constellation: {e}", type='negative')
                shareDialog.close()

            shareDialogShareBtn = ui.button('Share', on_click=share_constellation).style('flex: 1;')
            ui.button('Cancel', on_click=shareDialog.close).style('flex: 1;')

    #'Header' label
    with ui.row():
        ui.label('A Sky Full of Stars by Mythic Sky Mapper').style('font-size: 24px; font-weight: bold')

    #region buttons
    """
    #This doesn't do anything yet
    class NumStars:
        def __init__(self):
            self.numStars = 5
    num_stars_instance = NumStars()
    """

    # Control row and button group
    with ui.row().classes('items-center w-full'):
        #numStarsSlider = ui.slider(min=0, max=100, step=10).bind_value(num_stars_instance,'numStars').style('width: 200px') #Feature not yet implemented
        starSelectBtn = ui.button(icon='star',on_click=choose_star,color='primary').tooltip('Select stars, select the same star again to unselect')
        linkSelectBtn = ui.button(icon='link',on_click=choose_link,color='primary').tooltip('Select links, use Del key to delete')
        constellationSelectBtn = ui.button(icon='timeline',on_click=choose_constellation,color='primary').tooltip('Select constellations')
        
        #Register control buttons
        control_buttons.update({
            'starSelectBtn': starSelectBtn,
            'linkSelectBtn': linkSelectBtn,
            'constellationSelectBtn': constellationSelectBtn,
        })
        #Select starSelectBtn by default
        starSelectBtn.props('color=negative').update()

        with ui.button_group():
            constellationSaveBtn = ui.button(icon='save').tooltip('Save constellation')
            constellationDeleteBtn = ui.button(icon='delete').tooltip('Delete constellation')
            constellationShareBtn = ui.button(icon='share', on_click=shareDialog.open).tooltip('Share constellation')
            constellation_buttons.extend([constellationSaveBtn, constellationDeleteBtn, constellationShareBtn])
            constellation_action_buttons.extend([constellationSaveBtn, constellationDeleteBtn, constellationShareBtn])
            _toggle_constellationButtons(False) #disabled by default

            # Add delete handler
            def handle_delete_constellation():
                try:
                    if saved_constellations:
                        # Find the selected constellation by ID
                        const_ID = saved_constellations[-1]['id']
                        idx_to_remove = next((i for i, c in enumerate(saved_constellations) if c['id'] == const_ID), None)
                        if idx_to_remove is not None:
                            cursor.callproc('deleteConstellation', (const_ID,))
                            mydb.commit()
                            ui.notify('Constellation deleted!', type='positive')
                            # Remove that constellation from memory and from the working link set
                            removed = saved_constellations.pop(idx_to_remove)
                            removed_links = set(tuple(l) for l in removed.get('links', []))
                            if removed_links:
                                # purge from editable link structures as well, if present
                                global links_list, links_set
                                links_list = [e for e in links_list if e not in removed_links]
                                links_set = set(links_list)
                                _rebuild_links_from_list()
                            # Clear overlay and redraw remaining constellations
                            _clear_constellation_highlight()  # type: ignore
                            _draw_all_saved_constellations()  # type: ignore
                            _apply_to_plot()  # type: ignore
                            _toggle_constellation_action_buttons(False)
                    else:
                        ui.notify('No constellation selected to delete.', type='negative')
                except Exception as e:
                    ui.notify(f'Error deleting constellation: {e}', type='negative')
            constellationDeleteBtn.on('click', handle_delete_constellation)

        # Disable save, delete, and share buttons by default until a constellation is selected
        _toggle_constellation_action_buttons(False)

        ui.space()
        loginBtn = ui.button('Login', on_click=loginDialog.open).tooltip('Log in to share/save constellations')
    #endregion

    #region save constellation controls
    def save_constellation():
        global last_constellation_links,logged_in_user

        #Don't save if user is not logged in
        if not logged_in_user:
            ui.notify('Please log in to save constellations.', type='negative')
            return
        
        try:
            links_to_save = last_constellation_links if last_constellation_links else []
        except NameError:
            links_to_save = []
        
        constellation_name = constellationNameInput.value

        #Create the constellation in the database, get its ID
        cursor.callproc('createConstellation', (constellation_name,logged_in_user,))
        for result in cursor.stored_results():
                        row = result.fetchone()
        constellation_ID = row[0]  # type: ignore
        
        #Add the constellation to the in-memory list
        saved_constellations.append({'id': constellation_ID, 'name': constellation_name, 'links': links_to_save})

        #Add links to the database for this constellation
        for link in links_to_save:
            cursor.callproc('addLine', (constellation_ID, star_data[link[0]]['id'], star_data[link[1]]['id'],))
        
        mydb.commit()  #Commit after adding all lines

        ui.notify('Saved!', type='positive', position='top')
        #Update the graph
        _draw_all_saved_constellations()  # type: ignore
        _clear_constellation_highlight()  # type: ignore
        _apply_to_plot()  # type: ignore
    
    constellationSaveBtn.on('click', save_constellation)
    #endregion

    #region name of constellation controls
    with ui.row().classes('items-center'):
        ui.label('Constellation name:').style('margin-right: 8px;')
        constellationNameInput = ui.input().style('min-width: 180px;')
        constellationNameInput.disable()

    #Enable/disable constellationNameInput based on active_control
        # (Defined earlier)
    #endregion

    #region star map
    coords = SkyCoord(
        ra=[s['ra'] for s in star_data] * u.deg,  # type: ignore
        dec=[s['dec'] for s in star_data] * u.deg,  # type: ignore
        frame='icrs',
    )

    #Get the coordinates in the format Plotly wants
    lon = ((coords.ra.deg + 180) % 360) - 180   #RA → [-180°, +180°]  # type: ignore
    lat = coords.dec.deg  # type: ignore


    #plotly figure
    fig = go.Figure()
    fig.update_layout(clickmode='event')


    #Traces that make parts of the plot visible and/or selectable
    #Make each link FIRST (so it renders underneath later marker traces)
    fig.add_trace(go.Scattergeo(
        lon=[], lat=[],
        mode='lines',
        line=dict(color='blue', width=3),
        name='link',
    ))

    #Invisible large star star_hit markers to ease clicking
    fig.add_trace(go.Scattergeo(
        lon=lon, lat=lat,
        mode='markers',
        marker=dict(size=22, color='rgba(0,0,0,0)'),  #0s => invisible
        hoverinfo='skip',
        name='star_hit',
        showlegend=False,
    ))

    #Visible stars
    fig.add_trace(go.Scattergeo(
        lon=lon, lat=lat,
        mode='markers',
        marker=dict(size=6, color='black'),
        hoverinfo='text',
        text=[f"Star {s['id']}: RA={s['ra']}, Dec={s['dec']}" for s in star_data],
        name='stars',
    ))

    #Selected star highlight
    fig.add_trace(go.Scattergeo(
        lon=[], lat=[],
        mode='markers',
        marker=dict(size=18, color='red', line=dict(color='rgba(255,255,0,0.85)', width=3)),
        name='selection',
        showlegend=False,
    ))

    #Selected link highlight
    fig.add_trace(go.Scattergeo(
        lon=[], lat=[],
        mode='lines',
        line=dict(color='red', width=5),
        name='link_selected',
        showlegend=False,
    ))

    #Selected constellation highlight (group of links)
    fig.add_trace(go.Scattergeo(
        lon=[], lat=[],
        mode='lines',
        line=dict(color='orange', width=6),
        name='constellation_selected',
        showlegend=False,
    ))

    #Saved constellations overlay (distinct from current selection)
    fig.add_trace(go.Scattergeo(
        lon=[], lat=[],
        mode='lines',
        line=dict(color='goldenrod', width=6),
        name='constellations_saved',
        showlegend=False,
    ))

    #Lots of invisible points per curve position to make links clickable
    fig.add_trace(go.Scattergeo(
        lon=[], lat=[],
        mode='markers',
        marker=dict(size=32, color='rgba(0,0,0,0)'),  #0s => invisible
        name='link_hit',
        hoverinfo='none',
        showlegend=False,
    ))

    # Plot config and helpers (now that fig/plot exist)
    PLOTLY_CONFIG = {
        'scrollZoom': False,
        'doubleClick': False,
        'displayModeBar': False,
    }

    


    

    

    #Return all links connected to the given link as a constellation (connected component)
    def _build_constellation_from_link(link: tuple[int,int]) -> list[tuple[int,int]]:
        if not links_list:
            return []
        #Build adjacency of stars
        adj: dict[int, set[int]] = {}
        for a, b in links_list:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        #BFS/DFS from the two endpoints
        start_a, start_b = link
        stack = [start_a, start_b]
        seen: set[int] = set()
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            for m in adj.get(n, ()): stack.append(m)
        #Collect all links whose endpoints are within seen
        comp_links = [(a, b) for (a, b) in links_list if a in seen and b in seen]
        return comp_links

    

    

    #map appearance: frame & 30° grid visible
    fig.update_geos(
        projection_type='mollweide',
        showframe=True,
        framecolor='black',
        #Uncomment to show grid lines
        #lonaxis=dict(showgrid=True, dtick=30,
        #            gridcolor='rgba(0,0,0,0.3)', gridwidth=1),
        #lataxis=dict(showgrid=True, dtick=30,
        #            gridcolor='rgba(0,0,0,0.3)', gridwidth=1),
        showland=False, showcountries=False, showcoastlines=False, #this ain't a map of the earth we're looking at
    )
    plotHeight=750
    fig.update_layout(
        #title='Interactive Star Map – pan/zoom disabled', #Change/uncomment if you think we need a title on the graph
        dragmode=False,        #Don't allow drag‑pan or box zoom
        margin=dict(l=0, r=0, t=40, b=0),
        height=plotHeight,
    )

    #Add to the UI
    plot = ui.plotly(fig).style('width: 100%; height: ' + str(plotHeight + 10) + 'px;')
    plot._props.setdefault('options', {})['config'] = PLOTLY_CONFIG
    plot.update()                                 #push initial options
    #endregion

    # Helpers that depend on fig/plot
    PLOTLY_CONFIG = {
        'scrollZoom': False,
        'doubleClick': False,
        'displayModeBar': False,
    }

    def _apply_to_plot():
        plot._props['options']['config'] = PLOTLY_CONFIG
        plot.update()

    def _trace_index(name: str) -> int:
        for i, tr in enumerate(fig.data):
            if getattr(tr, 'name', None) == name:
                return i
        raise ValueError(f'Trace with name {name!r} not found')

    def _clear_star_highlight():
        try:
            si = _trace_index('selection')
            fig.data[si].lon, fig.data[si].lat = [], []
        except ValueError:
            pass

    def _clear_link_highlight():
        try:
            li = _trace_index('link_selected')
            fig.data[li].lon, fig.data[li].lat = [], []
        except ValueError:
            pass

    def _clear_constellation_highlight():
        try:
            ci = _trace_index('constellation_selected')
            fig.data[ci].lon, fig.data[ci].lat = [], []
        except ValueError:
            pass

    # Geometry helpers
    def _wrap180(x: float) -> float:
        return ((x + 180.0) % 360.0) - 180.0

    N_CURVE_SAMPLES = 64
    N_HIT_MARKERS = 9

    def _gc_path_lons_lats(i: int, j: int, samples: int | None = None):
        if samples is None:
            samples = N_CURVE_SAMPLES
        c1, c2 = coords[i], coords[j]
        sep = c1.separation(c2)  # type: ignore
        pa  = c1.position_angle(c2)  # type: ignore
        fracs = np.linspace(0.0, 1.0, samples)
        pts = [c1.directional_offset_by(pa, sep * f) for f in fracs]  # type: ignore
        lon_deg = [_wrap180(p.ra.deg) for p in pts]
        lat_deg = [p.dec.deg         for p in pts]
        out_lon, out_lat = [lon_deg[0]], [lat_deg[0]]
        for k in range(1, len(lon_deg)):
            if abs(lon_deg[k] - lon_deg[k-1]) > 180 - 1e-6:
                out_lon.append(None); out_lat.append(None)  # type: ignore
            out_lon.append(lon_deg[k]); out_lat.append(lat_deg[k])
        return out_lon, out_lat

    # Render helpers
    def _draw_links_into_trace(links: list[tuple[int,int]], trace_name: str):
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

    def _draw_all_saved_constellations():
        all_links: list[tuple[int,int]] = []
        for c in saved_constellations:
            if c.get('links'):
                all_links.extend(c['links'])
        _draw_links_into_trace(all_links, 'constellations_saved')

    # UI coloring and mode helpers are defined earlier; using them here

    #region click interaction
    selected: list[int] = []              #current (partial) pair, 0–2 indices
    links_lon: list[float|None] = []      #accumulated link segment longitudes (with None separators)
    links_lat: list[float|None] = []      #accumulated link segment latitudes
    links_set: set[tuple[int,int]] = set()  #store unique undirected links (i<j)
    selected_link: tuple[int, int] | None = None  #For link deletion
    links_list: list[tuple[int, int]] = []   #keeps (a,b) in the SAME order as links_lon/lat
    N_CURVE_SAMPLES = 64      #drawing detail for each link (curvature)
    N_HIT_MARKERS   = 9       #click targets per link along the curve

    

    def _rebuild_links_from_list():
        global links_lon, links_lat
        links_lon, links_lat = [], []

        hit_lon, hit_lat, hit_link = [], [], []
        for e_idx, (i, j) in enumerate(links_list):
            #visible curved blue path (+ None separator)
            LON, LAT = _gc_path_lons_lats(i, j, N_CURVE_SAMPLES)
            links_lon.extend(LON + [None]); links_lat.extend(LAT + [None])

            #many invisible click targets along the curve
            c1, c2 = coords[i], coords[j]
            sep = c1.separation(c2); pa = c1.position_angle(c2)  # type: ignore
            for f in np.linspace(0.1, 0.9, N_HIT_MARKERS):
                p = c1.directional_offset_by(pa, sep * f)  # type: ignore
                hit_lon.append(_wrap180(p.ra.deg))
                hit_lat.append(p.dec.deg)
                hit_link.append(e_idx)

        link_idx     = _trace_index('link')
        link_hit_idx = _trace_index('link_hit')

        fig.data[link_idx].lon,     fig.data[link_idx].lat     = links_lon, links_lat
        fig.data[link_hit_idx].lon, fig.data[link_hit_idx].lat = hit_lon,   hit_lat
        fig.data[link_hit_idx].customdata = hit_link

    def handle_click(e: events.GenericEventArguments):
        global selected_link, selected

        stars_idx           = _trace_index('stars')
        star_hit_idx        = _trace_index('star_hit')
        link_hit_idx        = _trace_index('link_hit')
        selected_star_idx   = _trace_index('selection')

        pts = e.args.get('points') or []
        if not pts:
            return

        match active_control:
            case 'constellationSelectBtn':
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

            case 'linkSelectBtn':
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
                selected_link = links_list[link_num]
                i, j = selected_link
                LON, LAT = _gc_path_lons_lats(i, j, N_CURVE_SAMPLES)
                sel_idx = _trace_index('link_selected')
                fig.data[sel_idx].lon, fig.data[sel_idx].lat = LON, LAT
                _apply_to_plot()
                return

            case 'starSelectBtn':
                p = next((p for p in pts if p.get('curveNumber') in (stars_idx, star_hit_idx)), None)
                if not p:
                    return
                idx = p.get('pointIndex', p.get('pointNumber'))
                if idx is None:
                    return
                if len(selected) == 1 and selected[0] == idx:
                    selected.clear()
                    fig.data[selected_star_idx].lon = []
                    fig.data[selected_star_idx].lat = []
                    _apply_to_plot()
                    return
                if idx not in selected:
                    selected.append(idx)
                if len(selected) > 2:
                    selected[:] = selected[-2:]
                fig.data[selected_star_idx].lon = [lon[i] for i in selected]
                fig.data[selected_star_idx].lat = [lat[i] for i in selected] #type: ignore
                if len(selected) == 2:
                    i, j = selected
                    a, b = (i, j) if i < j else (j, i)
                    if a != b and (a, b) not in links_set:
                        links_set.add((a, b))
                        links_list.append((a, b))
                        _rebuild_links_from_list()
                    selected.clear()
                    fig.data[selected_star_idx].lon = []
                    fig.data[selected_star_idx].lat = []
                _apply_to_plot()

    plot.on('plotly_click', handle_click)           #hook JS → Python

<<<<<<< HEAD
                selected.clear()
                fig.data[selection_idx].lon = []
                fig.data[selection_idx].lat = []

            _apply_to_plot()

    plot.on('plotly_click', handle_click)           # hook JS → Python

    def load_user_constellations(username: str):
        """Load all constellations for the given user from the database."""
        global saved_constellations, links_list, links_set
        saved_constellations = []
        links_list = []
        links_set = set()
        # ...fetch constellations from DB...
        for constellation in fetched_constellations:
            # constellation['links'] should be a list of (i, j) tuples
            saved_constellations.append(constellation)
            links_list.extend(constellation['links'])
            for link in constellation['links']:
                links_set.add(link)
        _rebuild_links_from_list()
        _apply_to_plot()
    # TODO: Implement logic to fetch and store user's constellations
    pass

    # Listen for Del key to delete selected link
=======
    #Listen for Del key to delete selected link
>>>>>>> origin
    def _is_delete_key(e: events.KeyEventArguments) -> bool:
        k = getattr(e, 'key', None)
        if isinstance(k, str):                      #older NiceGUI: key is a plain str
            name, code = k, ''
        else:                                       #newer: key is an object with .name/.code
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

            #rebuild both traces from the ordered list
            _rebuild_links_from_list()

            #clear red overlay
            link_sel_idx = _trace_index('link_selected')
            fig.data[link_sel_idx].lon = []
            fig.data[link_sel_idx].lat = []
            selected_link = None

            _apply_to_plot()
            #ui.notify('link deleted.', type='info', position='top')

    def _on_key(e: events.KeyEventArguments):
        if getattr(e.action, 'keydown', False) and _is_delete_key(e):
            _delete_selected_link()

    #Create the global keyboard listener
    ui.keyboard(on_key=_on_key)
    #endregion

    #Close the database connection
    def cleanup():
        if 'cursor' in locals():
            cursor.close()
        if 'mydb' in locals() and mydb.is_connected():
            mydb.close()
            print("MySQL connection closed.")

    #ui.on_disconnect(cleanup)
    #Start the UI
    ui.run()

except mysql.connector.Error as err:
    print(f"Error connecting to MySQL: {err}")