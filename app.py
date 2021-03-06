from flask import Flask
from flask import render_template, request, redirect, send_file, url_for, g
from flask import flash, send_from_directory, jsonify
from datetime import datetime, timedelta
import json
import psycopg2
import os
import queries as db

app = Flask(__name__)

IMG_FOLDER = os.path.join(os.getcwd(), 'static', 'img')
app.config['IMG_FOLDER'] = IMG_FOLDER
app.secret_key = 'supersupersupersecret'

@app.before_request
def load_user():
    user_info = json.loads(request.headers.get('X-KVD-Payload'))
    g.userinfo = user_info
    g.username = user_info['user']
    g.mail = user_info['email']
    g.name = "{} {}".format(user_info['firstname'], user_info['lastname'])
    db.add_or_update_user(g.username, g.mail, g.name)
    g.isadmin = db.check_user_admin(g.username)
    #TODO move this into the database
    g.translation = {"BAT": "Battery", "CO2": "Carbon Dioxide",
		      "HUMB": "Humidity", "O3": "Ozone",
		      "TCA": "Temperature", "NO2": "Nitrogen Dioxide",
		      "CO": "Carbon Monoxide"}

# VISIBLE PAGES BELOW -----------------------------------------------------------

# default - map view
@app.route("/")
@app.route("/map")
def map_page():
  debug = None
  sensors = db.get_sensor_list()

  return render_template("maps.html", page_title="microcats | map view",
    site_name="microcats", username=g.username,
    sensors=sensors, translations=g.translation,
    isadmin = g.isadmin,
    debug=debug)

# about - lists all sensors + statistics
@app.route("/about")
def about_page():
  debug = None
  station_list = db.get_all_station_info()
  station_info = []
  for sid, desc, name, x, y in station_list:
    station = {}
    station["sid"] = sid
    station["desc"] = desc
    station["name"] = name
    station["location"] = "{},{}".format(x,y)
    station["birthday"] = db.get_birthday(sid)
    station["values"] = get_station_stats(sid)
    station["last"] = db.get_last_reading_time(sid)
    station["status"] = get_station_status(sid)
    station_info.append(station)

  return render_template("about.html", page_title="microcats | sensors",
    site_name="microcats", username=g.username,
    station_info=station_info,
    isadmin = g.isadmin,
    debug=debug)

# feed - view stream of messages coming in from meshlium
@app.route("/feed")
def feed_page():
  debug = None
  msgs = []
  with app.open_resource('logs/mqtt.log') as f:
    for line in f:
      info = {}
      bits = line.strip().split("|")
      for bit in bits:
	info[bit.split(":",1)[0].strip()] = bit.split(":",1)[1].strip()
      msgs.append(info)

  return render_template("feed.html", page_title="microcats | data feed",
    site_name="microcats", username=g.username,
    msgs=msgs,
    isadmin = g.isadmin,
    debug=debug)

# viz - view visualisations
@app.route("/viz")
def visualisations_page():
  debug = None
  station_list = db.get_all_station_info()
  sensor_list = db.get_sensor_list()

  return render_template("graphs.html", page_title="microcats | visualisations",
    site_name="microcats", username=g.username,
    station_list=station_list,
    sensor_list=sensor_list,
    isadmin = g.isadmin,
    debug=debug)

# shows information about each specific sensor
@app.route("/sensor/<name>", 
  methods=['GET', 'POST'])
def station_info_page(name):
  debug = None
  sid = db.get_id_from_name(name)
  station_info = db.get_station_info(sid)
  if (not station_info):
    station_info = (None, None, None, None, None)
  (_, desc, name, x, y) = station_info
  station = {}
  station["sid"] = sid
  station["desc"] = desc
  station["name"] = name
  station["location"] = "{},{}".format(x,y)
  station["birthday"] = db.get_birthday(sid)
  station["values"] = get_station_stats(sid)
  station["last"] = db.get_last_reading_time(sid)
  station["status"] = get_station_status(sid)
  vals = get_station_stats(sid)
  return render_template("station.html", page_title="microcats | " + name,
    site_name="microcats", username=g.username, 
    station=station, vals=vals, translations=g.translation,
    isadmin = g.isadmin,
    debug=debug)

# api documentation guide
@app.route("/doco")
def api_doco_page():
  debug = None
  url = "https://microcats.uqcloud.net"
  command_list = [
    {"path": "/get/stations", 
      "desc": """This query returns a list of stations and information about 
	    each station."""},
    {"path": "/get/sensors", 
      "desc": """ This query returns a list of codes for each sensor type 
      attached to the sensor nodes, along with a translation of the variable 
      it measures."""},
    {"path": "/get/uptime/<sid>",
      "desc":  """This query returns a count of the number of readings sent by a station per day for the period of one year. The sensor id must be 
      specified. """},
    {"path": "/get/readings/<attr>",
      "desc": """This query returns readings from all stations for the
      specified sensor type. Without any additional parameters given, it
      returns the most recently obtained readings."""},
    {"path": "/get/readings/<attr>/<time_from>",
      "desc":  """If the optional <time_from> parameter is given, this
      query returns all readings for the specified sensor type from all
      stations, from the time specified to the present."""},
    {"path": "/get/readings/<attr>/<time_from>/<time_to>",
      "desc":  """If both the time_from and time_to parameters are given, 
      this query returns all readings for the specified sensor type from all 
      stations, between (and including) the start and end times."""},
    {"path": "/get/hour-average/<sid>/<attr>/<time_from>/<time_to>",
      "desc": """This query returns hourly aggregated values from readings
      for a specified station and sensor, for every hour from the start time
      to the end time."""},
    {"path": "/get/day-average/<sid>/<attr>/<time_from>/<time_to>",
      "desc":  """This query returns daily aggregated values from readings
      for a specified station and sensor, for every day from the start time
      to the end time."""}
  ]
  return render_template("doco.html", page_title="microcats | api documentation",
    site_name="microcats", username=g.username,
    url=url, command_list=command_list,
    isadmin = g.isadmin,
    debug=debug)

# user management page
@app.route("/manage/users")
def user_management_page():
  debug = None
  if (not g.isadmin):
      return redirect(url_for('map_page'))
  req = db.get_all_users()
  admins = []
  users = []
  for _, uid, role, _, name in req:
    info = {}
    info['uid'] = uid
    info['role'] = role
    if (name):
      info['name'] = name
    else:
      info['name'] = uid
    if (role == 'user'):
      users.append(info)
    else:
      admins.append(info)
  return render_template("users.html", page_title="microcats | user management",
    site_name="microcats", username=g.username,
    users=users, admins=admins,
    isadmin = g.isadmin,
    debug=debug)

# progress seminar presentation
@app.route("/pp")
def progress_seminar_presentation():
  return render_template("progress_seminar.html", page_title="thesis progress seminar")

# API PAGES BELOW -----------------------------------------------------------

# return station information as json
@app.route("/get/stations")
def get_stations():
  station_json = {'stations': []}
  query = db.get_all_station_info()

  for sid, description, name, x, y in query:
    birthday = db.get_birthday(sid)
    last_contact = db.get_last_reading_time(sid)
    new_station = {"name": name, "station_ID": sid, "x_coord": x, "y_coord": y}
    new_station['description'] = description
    new_station['birthday'] = str(birthday)
    new_station['last_contact'] = str(last_contact)
    new_station['status'] = get_station_status(sid)
    station_json['stations'].append(new_station)

  return jsonify(station_json)

# return sensor information as json
@app.route("/get/sensors")
def get_sensors():
  sensor_json = {'sensors': {}}
  query = db.get_sensor_list()

  for i, sensor in query:
    sensor_json['sensors'][sensor] = g.translation.get(sensor, "")
  return jsonify(sensor_json)

# return readings from all sensors as json
# optional: specify time from and time to to limit result set
@app.route("/get/readings/<attr>", methods=['GET', 'POST'], 
  defaults={'time_from': None, 'time_to': None})
@app.route("/get/readings/<attr>/<time_from>", methods=['GET', 'POST'], 
  defaults={'time_to': None})
@app.route("/get/readings/<attr>/<time_from>/<time_to>", 
  methods=['GET', 'POST'])
def get_readings(attr, time_from, time_to):
  if (attr == 'CAT'):
    return render_template("cats.html", page_title="DID YOU ASK FOR CATS",
      site_name="microcats", username=g.username)
  else:
    station_list = db.get_all_station_info()
    result_json = {'results': {}}

    for station in station_list:
      sid = station[0]
      sensor_data = []
      if (not time_to):
        if (time_from):
          data = db.get_closest_reading(int(sid), attr.upper(), time_from)
        else:
          data = db.get_closest_reading(int(sid), attr.upper(), datetime.now())
      else:
        data = db.get_readings_between(int(sid), attr.upper(), time_from, time_to)
      if (not data):
        return jsonify({ 'err': "No results found for query" })
      for sensor, value, time in data:
        reading = {}
        reading[sensor] = value
        reading['time'] = time
        sensor_data.append(reading)
      result_json['results'][str(sid)] = sensor_data
    return jsonify(result_json)

# return hourly aggregated values calculated from readings from a specific station+sensor as json
@app.route("/get/hour-average/<sid>/<attr>/<time_from>/<time_to>", 
  methods=['GET', 'POST'])
def get_readings_hourly_average(sid, attr, time_from, time_to):
  result_json = {'results': []}

  data = db.get_hourly_average(int(sid), attr.upper(), time_from, time_to)
  if (not data):
    return jsonify({ 'err': "No results found for query" })
  for value, time in data:
    sensor_data = {}
    sensor_data['time'] = str(time)
    sensor_data['value'] = float(value)
    result_json['results'].append(sensor_data)
  return jsonify(result_json)

# return daily aggregated values calculated from readings from a specific station+sensor as json
@app.route("/get/day-average/<sid>/<attr>/<time_from>/<time_to>", 
  methods=['GET', 'POST'])
def get_readings_daily_average(sid, attr, time_from, time_to):
  result_json = {'results': []}

  data = db.get_daily_average(int(sid), attr.upper(), time_from, time_to)
  if (not data):
    return jsonify({ 'err': "No results found for query" })
  for value, time in data:
    sensor_data = {}
    sensor_data['time'] = str(time)
    sensor_data['value'] = float(value)
    result_json['results'].append(sensor_data)
  return jsonify(result_json)

# return count of readings sent by a specific station per day as json
@app.route("/get/uptime/<sid>", methods=['GET', 'POST'])
def get_station_uptime(sid):
  result_json = {'results': {}}
  data = db.get_uptime(int(sid))
  if (not data):
    return jsonify({ 'err': "No results found for query" })
  for time, count in data:
    date = str(time).split(" ", 1)[0]
    result_json['results'][date] = count
  return jsonify(result_json)

# FORM INTERACTION PAGES BELOW -----------------------------------------------

# add new administrator
@app.route('/_new_admin', methods=['GET', 'POST'])
def add_new_admin():
  result = None
  msg = None
  result_json = {'result': result, 'msg': msg}
  uid = request.args.get('uid', -1, type=unicode)
  name = request.args.get('name', -1, type=unicode)
  mail = request.args.get('mail', -1, type=unicode)
  query = db.add_new_admin(uid, name, mail)
  if (not g.isadmin):
    result = "error"
    msg = "You don't have permissions to manage administrators!"
    return jsonify(result_json)
  else:
    if (not query):
      result = "error"
      msg = "Could not add " + uid + " as administrator"
    else:
      result = "success"
      msg = "Added " + uid + " as administrator"
    result_json['result'] = result
    result_json['msg'] = msg
    return jsonify(result_json)

# modify user privileges
@app.route('/_mod_admin', methods=['GET', 'POST'])
def mod_admin():
  result = None
  msg = None
  result_json = {'result': result, 'msg': msg}
  if (not g.isadmin):
    result = "error"
    msg = "You don't have permissions to manage administrators!"
    return jsonify(result_json)
  else:
    uid = request.args.get('uid', -1, type=unicode)
    act = request.args.get('action', -1, type=unicode)
    if (act == "add"):
      query = db.user_to_admin(uid)
      if (not query):
        result = "error"
        msg = "Could not add " + uid + " as administrator"
      else:
        result = "success"
        msg = "Added " + uid + " as administrator"
    else:
      query = db.admin_to_user(uid)
      if (not query):
        result = "error"
        msg = "Could not remove administrator privileges from " + uid
      else:
        result = "success"
        msg = "Removed administrator privileges from  " + uid
    result_json['result'] = result
    result_json['msg'] = msg
    return jsonify(result_json)

# modify station information
@app.route('/_update_sensors', methods=['GET', 'POST'])
def update_sensors():
  if (not g.isadmin):
    msg = "You don't have permissions to manage administrators!"
  else:
    [sid, field] = request.form['id'].split("-")
    sid = int(sid)
    val = request.form['value'].strip()

    if (field == "name"):
      msg = db.update_sensor_name(sid, val)
    elif (field == "desc"):
      msg = db.update_sensor_desc(sid, val)
    elif (field == "coord"):
      val = (" ").join(val.split(","))
      msg = db.update_sensor_loc(sid, val)
    else:
      msg = "error"

  return msg

# MISC PAGES BELOW -----------------------------------------------------------

# enable direct access of image files in static/img/
@app.route('/img/<path:filename>')
def serve_static(filename):
  return send_from_directory(app.config['IMG_FOLDER'], filename)

# calculate and format highest, lowest, average readings for each sensor type
def get_station_stats(sid):
  attrs = db.get_sensor_list()
  vals = {}
  for i, attr in attrs:
    reading = db.get_closest_reading(sid, attr.upper(), datetime.now())
    if reading:
      (sensor,value,time) = reading[0]
      vals[sensor] = []
      highest = db.get_highest_reading(sid, attr.upper());
      lowest = db.get_lowest_reading(sid, attr.upper());
      average = db.get_average_reading(sid, attr.upper());
      vals[sensor].append(highest)
      vals[sensor].append(lowest)
      vals[sensor].append("{0:.2f}".format(average))
  return vals

# calculate station status (active/inactive)
def get_station_status(sid):
  last = db.get_last_reading_time(sid)
  status = None
  min_diff = None
  if last:
    diff = datetime.now() - last
    min_diff = abs(divmod(diff.total_seconds(), 60)[0])
    if min_diff < 20:
      return "Active"
  return "Inactive"

if __name__ == "__main__":
  app.run(debug=True)
