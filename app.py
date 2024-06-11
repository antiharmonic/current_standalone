#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
import records
#import ConfigParser
import argparse, argcomplete
from configparser import ConfigParser, ExtendedInterpolation
import os
from texttable import Texttable
import pydoc
import inflect
import re
from datetime import date, datetime
# determine args/usage
# current --push --movie "movie title"
# current --random --movie
# pushcurr --movie "movie title"
# current --push --type=movie "movie title"

# create table current_media (id serial primary key, title citext, type int references media_type(id), weight numeric default 1, date_added date default now(), unique(title+type));

type_unit = {
  '1': 1,
  '2': 2,
  '4': 1,
  '6': 2,
  '3': 2,
  '7': 2,
  '8': 2,
  '9': 2,
  '10': 1,
  '11': 2,
  '12': 2,
  '13': 2,
  '14': 2
}

p = inflect.engine()

def format_media(rows, format='table'):
  if format == 'titles':
    return "\n".join((r['title'] for r in rows))
  else:
    rows = [[m['id'], m['title'], mlookup[m['type']], m['weight'], m['date_added'], m['started'] or "", m['removed'] or "", "Yes" if m['priority'] else "", m['referrer'] or "", reason_lookup.get(m.get('reason', None), ""), m['genre'] or "", m.get('estimated_length', "") or "", m['music_theme_url'] or "", m.get('deferred', '') or ''] for m in rows]

    rows.insert(0, ["ID", "Title", "Type", "Weight", "Date Added", "Started", "Removed", "Priority?", "Referrer", "Reason", "Genre", "Length", "Theme", "Deferred"])
    tbl = Texttable()
    tbl.add_rows(rows)
    tbl.set_max_width(0)
    return tbl.draw()


def argDateType(d):
  date = re.match("^(\d\d\d\d-\d\d-\d\d)$", d)
  try:
    return date[0]
  except TypeError as e:
    raise ValueError(f"{d} is not a valid date")


def media_type(type):
  try:
    return _mtype[type]
  except KeyError as e:
    print(f"Media type {type} not recognized")
    exit()

class StoreMediaTypeAction(argparse.Action):
  def __init__(self, option_strings, dest, nargs=None, **kwargs):
    if nargs is not None:
      raise ValueError("nargs not allowed")
    super().__init__(option_strings, dest, **kwargs)
  def __call__(self, parser, namespace, values, option_string=None):
    print('%r %r %r' % (namespace, values, option_string))
    print(self.dest)
    setattr(namespace, self.dest, media_type(values))


def subparser_uses_title_or_id(sp):
  #TODO add action def so that 
  # 1) title is changed to string
  # 2) converted to int, stored in id, and set to None if by-id is True
  # refactoring!
  sp.add_argument('title', nargs='+')
  sp.add_argument('--by-id', dest='id', action='store_true')


def add_types_to_subparser(sp, required=True, by_id=False):
  exclusive_media = sp.add_mutually_exclusive_group(required=required)
  exclusive_media.add_argument('--type', action=StoreMediaTypeAction)
  exclusive_media.add_argument('--movie', '--movies', '--film', '--films', dest='type', action='store_const', const=media_type('movie'),)
  exclusive_media.add_argument('--show', '--shows', '--tv', dest='type', action='store_const', const=media_type('tv show'))
  exclusive_media.add_argument('--book', '--books', dest='type', action='store_const', const=media_type('book'))
  exclusive_media.add_argument('--game', '--games', dest='type', action='store_const', const=media_type('video game'))
  exclusive_media.add_argument('--vidya', '--video-game', '--video-games', dest='type', action='store_const', const=media_type('video game'))
  exclusive_media.add_argument('--anime', dest='type', action='store_const', const=media_type('anime'))
  exclusive_media.add_argument('--comic', '--comics', dest='type', action='store_const', const=media_type('comic book'))
  exclusive_media.add_argument('--album', '--albums', '--music', dest='type', action='store_const', const=media_type('album'))
  if by_id:
    exclusive_media.add_argument('--by-id', dest='id', action='store_true')
  return exclusive_media

def add_theme_to_subparser(sp):
  sp.add_argument('--theme', type=str)

def add_genre_to_subparser(sp):
  sp.add_argument('--genre', type=str)

def add_reason_to_subparser(sp):
  sp.add_argument('--reason', choices=list(reasons.keys()))

def assert_single_record(title, type, pred):
  sql = "select count(*) as count from current_media" + pred
  res = db.query(sql, title=title, type=type).first()
  msg = None
  if res.count > 1:
    msg = "More than one matching record found"
  elif res.count < 1:
    msg = "No matching records found"
  if msg:
    raise ValueError(msg)


def parse_title_id(args, title_bind=":title"):
  title = ' '.join(args.title)
  id = args.id
  if args.id:
    type = None
  else:
    type = args.type
  if id:
    sql = f" where id = {title_bind}"
  else:
    sql = f" where title = {title_bind} and type = :type"
  return title, id, type, sql


def push_media(args):
#  print(args)
  title = ' '.join(args.title)
  total = count_base(args, True)
  if total >= 4 and args.priority:
    print(f"WARNING: Already have {total} {p.plural(mlookup[args.type].lower())}")
  print(f"Adding {mlookup[args.type]} \"{title}\".")
  db.query("insert into current_media (title, type, referrer, priority, weight, genre, estimated_length, reason, music_theme_url) values (:title, :type, :referrer, :priority, :weight, :genre, :hours, :reason, :theme) on conflict (title, type) do update set weight = current_media.weight + :weight", title=title, type=args.type, referrer=args.referrer, priority=args.priority, weight=args.weight, genre=args.genre, hours=args.hours, reason=reasons.get(args.reason, None), theme=args.theme)


def update_media(args):
  title, id, type, sql_pred = parse_title_id(args)
  sql = "update current_media "
  updates = list()
  ##TODO for now we'll be skipping updating of date which can be changed with /start/ and type which we'll keep unchangeable
  if args.genre:
    updates.append("set genre = :genre")
  if args.referrer:
    updates.append("set referrer = :referrer")
  if args.weight:
    updates.append("set weight = :weight")
  if args.deferred:
    updates.append("set deferred = now()")
  if args.reason:
    updates.append("set reason = :reason")
  if args.length:
    updates.append("set estimated_length = :length")
  if args.theme:
    updates.append("set music_theme_url = :theme")
  if not updates:
    print("No changes processed, refusing database update")
    return
  sql += ", ".join(updates)
  sql += sql_pred
  #print(sql)
  db.query(sql, id=id, title=title, type=type, length=args.length, referrer=args.referrer, genre=args.genre, weight=args.weight, reason=reasons.get(args.reason, None), theme=args.theme)


def random_media(args):
  # weighted random so that e.g. a movie i've pushed several times or really want to watch and manually overrode will be more likely to come
  # https://stackoverflow.com/questions/1398113/how-to-select-one-row-randomly-taking-into-account-a-weight
  sql = "select id, title, weight, date_added, started, removed, referrer, genre, type, -log(random())/weight as priority from current_media where removed is null and deferred is null";
  if args.type:
    sql += " and type = :type"
  if args.genre:
    sql += " and lower(genre) like '%' || lower(:genre) || '%'"
  sql += " order by priority limit :limit"
  rows = db.query(sql, limit=args.count, type=args.type, genre=args.genre).as_dict()
  print(format_media(rows))


def remove_media_func(args, remove=False):
  title, id, type, sql_pred = parse_title_id(args)
  #print(f"Attempting to remove \"{title}\" from current media list")
  # are we going to delete or archive in some way? maybe just add a column called "popped" and filter it out of other queries.
  sql = "select *, now() at time zone 'America/Chicago' as now from current_media" + sql_pred
  data = db.query(sql, title=title, type=args.type, id=args.id).as_dict()[0]

  if not data:
    print("Could not find media")
    exit()

  try:
    if args.rename:
      data['title'] = args.rename
  except AttributeError:
    pass

  if data['started'] is None:
    data['started'] = data['now']
  if remove == False:
    sql = "insert into media (title, subsection, begin_date, end_date, media_type, length, length_unit, from_current_media_id, music_theme_url) values (:title, :subsection, :begin, now() at time zone 'America/Chicago', :type, :length, :unit, :id, :theme) returning *"
    # todo update music_theme_title here or? maybe add some background job to check null theme_titles where theme_urls or idk
    try:
      res = db.query(sql, title=data['title'], begin=data['started'], type=data['type'], length=data['estimated_length'], unit=type_unit[str(data['type'])], id=data['id'], subsection=args.subsection, theme=(args.theme or data['music_theme_url']).as_dict()[0]
    except Exception as e:
      print(f"Unable to remove {data.title} from current media list: {e}")
      exit()
  sql = "update current_media "
  if args.theme:
    sql += "set music_theme_url = :theme, "
  sql += "set removed = now() at time zone 'America/Chicago' where id = :id"
  if remove == False:
    print(f"Removed {data['title']} and added to table media as {res['id']}: {res['title']}")
  else:
    print(f"Removed {data['title']}.")
  db.query(sql, id=data['id'], theme=args.theme)


def pop_media(args):
  return remove_media_func(args, False)


def remove_media(args):
  return remove_media_func(args, True)


def start_media(args):
  title, id, type, sql_pred = parse_title_id(args)
  print(f"attempting to start media (for date {args.date})")
  #title = ' '.join(args.title)
  
 # sql = "update current_media set started = to_date(:start_date) + interval '6 hours' at time zone 'America/Chicago'" + sql_pred
  sql = "update current_media set started = :start_date" + sql_pred
  #if id:
  #  sql += " where id = :id"
  #else:
  #  sql += " where title = :title and type = :type"
  # hackjob, not sure how to fix in a better way without using cursors or fixing the underlying issue in the media db which might actually have wrong data now (e.g dates off by one or two)
  db.query(sql, id=args.id, title=title, type=args.type, start_date=args.date)


def search_media(args):
  #TODO move this to action def
  id = None
  title = None
  if args.id:
    id = int(args.title[0])
    sql = "select * from current_media where id = :id"
  else:
    title = ' '.join(args.title)
    sql = "select * from current_media where title like '%' || :title || '%'"
  if args.type:
    sql += " and type = :type"
  rows = db.query(sql, title=title, type=args.type, id=id).as_dict()
  print(format_media(rows))


def recently_added(args):
  sql = "select *  from current_media where removed is null"
  if args.type:
    sql += " and type = :type"
  sql += " order by id desc limit :limit"
  rows = db.query(sql, type=args.type, limit=args.limit)
  print(format_media(rows))


def count_base(args, total=False):
  sql = "select count(*) as total from current_media where removed is null and deferred is null"
  if args.type:
    sql += " and type = :type"
  if not total:
    if args.priority:
      sql += " and priority = True"
    if args.reason:
      sql += " and reason = :reason"
  return db.query(sql, type=args.type, reason=reasons.get(args.reason, None)).first()['total']

def count_media(args):
  total = count_base(args)
  print(f"Found {total} matching records.")


def list_media(args):
  sql = "select * from current_media where deferred is null"
  if args.type:
    sql += " and type = :type"
  if args.genre:
    sql += " and lower(genre) like '%' || lower(:genre) || '%'"
  if args.reason:
    sql += " and reason = :reason"
  if args.todo:
    sql += " and removed is null"
  if args.order:
    # TODO get column names, ensure args.order is 1 or 2 words, 1 word is column name, 2nd word is asc or desc. for now doesn't really matter.
    # but sqli bad mmk
    cols = db.query("SELECT lower(column_name) as column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name   = 'current_media'").all()
    cols = [c.column_name for c in cols]
    order = args.order.split(" ")
    order_by = order[0].lower()
    order_sort = "asc"
    if len(order) > 1:
      order_sort = order[1].lower()
    if order_by in cols and order_sort in ("asc", "desc"):
      sql += f" order by {order_by} {order_sort}"
  else:
    sql += " order by title"

  rows = db.query(sql, type=args.type, genre=args.genre, reason=reasons.get(args.reason, None)).as_dict()
  if args.format == 'titles':
    print(format_media(rows, args.format))
  else:
    if len(rows) <= 10 or args.pager == False:
      print(format_media(rows))
    else:
      pydoc.pager(format_media(rows))

def top_media(args):
  sql = "select * from current_media where priority = true and removed is null and deferred is null"
  if args.type:
    sql += " and type = :type"
  #TODO
  sql += " order by date_added, title"
  rows = db.query(sql, type=args.type).as_dict()
  print(format_media(rows))



def prioritize_media(args, priority):
  title, id, type, sql = parse_title_id(args)
  assert isinstance(priority, bool), f"Expected boolean priority value, received {priority}"
  assert_single_record(title, type, sql)
  sql = "update current_media set priority = :priority" + sql
  db.query(sql, title=title, type=type, priority=priority)
  print(f"Reprioritized media {title} successfully")


def downgrade_media(args):
  prioritize_media(args, False)


def upgrade_media(args):
  prioritize_media(args, True)


def started_media(args):
  sql = "select * from current_media where started is not null and removed is null and deferred is null"
  if args.type :
    sql += " and type = :type"
  sql += " order by started"
  rows = db.query(sql, type=args.type).as_dict()
  print(format_media(rows))


# init

dir_path = os.path.dirname(os.path.realpath(__file__))
cfg = ConfigParser(interpolation=ExtendedInterpolation())
configfile=os.environ.get('APP_CONFIG_FILE', default=dir_path+'/config.ini')
cfg.read(configfile)
settings = dict(cfg.items('database'))
db = None

try:
  db = records.Database("postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}".format(**settings), pool_size=10)
except Exception as e:
  print(f"Unable to connect to the database: {e}")
  exit()

# get default/config/command values this will have to change in the api version probably i.e. just fail at the post and the user/command pulls from the same pkg or something
# maybe should use a bidict for this instead...
mt = db.query("select id, name from media_type").as_dict()
_mtype = {m['name'].lower(): m['id'] for m in mt}
mlookup = {m['id']: m['name'] for m in mt}

rq = db.query("select id, command from media_reason").as_dict()
reasons = {r['command']: r['id'] for r in rq}
reason_lookup = {r['id']: r['command'] for r in rq}
#_mtype = {'game': 0, 'movie': 1, 'show': 3, 'book': 5}
#print(_mtype)



# parse args
parser = argparse.ArgumentParser(description="Current media")
parser.add_argument('--debug', action='store_true')

subparsers = parser.add_subparsers()
push_parser = subparsers.add_parser('push', aliases=['add'])
push_parser.add_argument('title', nargs='+')
push_parser.add_argument('--weight', default=1)
push_parser.add_argument('--referrer')
push_parser.add_argument('--priority', action='store_true')
push_parser.add_argument('--top', dest='priority', action='store_true')
push_parser.add_argument('--genre')
push_parser.add_argument('--hours', '--pages', '--length', dest='hours', type=float) #refactor? i.e. rename hours everywhere to length for code clarity?
push_parser.add_argument('--deferred', '--defer', action='store_true')
add_types_to_subparser(push_parser)
add_reason_to_subparser(push_parser)
add_theme_to_subparser(push_parser)
push_parser.set_defaults(func=push_media)

pop_parser = subparsers.add_parser('pop')
pop_parser.add_argument('title', nargs='+')
pop_parser.add_argument('--rename', type=str)
pop_parser.add_argument('--subsection', type=str, default='')
add_theme_to_subparser(pop_parser)
group = add_types_to_subparser(pop_parser, by_id=True)
# REMOVE group.add_argument('--by-id', dest='id', action='store_true')
pop_parser.set_defaults(func=pop_media)

update_parser = subparsers.add_parser('update')
update_parser.add_argument('title', nargs='+')
update_parser.add_argument('--weight')
update_parser.add_argument('--referrer')
update_parser.add_argument('--genre')
update_parser.add_argument('--deferred', action='store_true')
update_parser.add_argument('--length', type=int)
add_theme_to_subparser(update_parser)
add_reason_to_subparser(update_parser)
group = add_types_to_subparser(update_parser, by_id=True)
update_parser.set_defaults(func=update_media)


rm_parser = subparsers.add_parser('rm', aliases=['remove', 'delete'])
rm_parser.add_argument('title', nargs='+')
group = add_types_to_subparser(rm_parser)
group.add_argument('--by-id', dest='id', action='store_true')
rm_parser.set_defaults(func=remove_media)

start_parser = subparsers.add_parser('start')
start_parser.add_argument('title', nargs='+')
start_parser.add_argument('--date', type=argDateType, default=date.today().strftime("%Y-%m-%d"))
group = add_types_to_subparser(start_parser, by_id=True)
start_parser.set_defaults(func=start_media)

random_parser = subparsers.add_parser('random')
random_parser.add_argument('--count', type=int, default=1)
add_types_to_subparser(random_parser, False)
add_genre_to_subparser(random_parser)
random_parser.set_defaults(func=random_media)

search_parser = subparsers.add_parser('search', aliases=['find'])
#search_parser.add_argument('title', nargs='+')
subparser_uses_title_or_id(search_parser)
add_types_to_subparser(search_parser, False)
search_parser.set_defaults(func=search_media)

count_parser = subparsers.add_parser('count')
count_parser.add_argument('--priority', action='store_true')
count_parser.add_argument('--top', dest='priority', action='store_true')
add_types_to_subparser(count_parser, False)
add_reason_to_subparser(count_parser)
count_parser.set_defaults(func=count_media)

downgrade_parser = subparsers.add_parser('downgrade')
downgrade_parser.add_argument('title', nargs='+')
group = add_types_to_subparser(downgrade_parser, by_id=True)
downgrade_parser.set_defaults(func=downgrade_media)

upgrade_parser = subparsers.add_parser('upgrade')
upgrade_parser.add_argument('title', nargs='+')
group = add_types_to_subparser(upgrade_parser, by_id=True)
upgrade_parser.set_defaults(func=upgrade_media)

recent_parser = subparsers.add_parser('recent', aliases=['latest'])
recent_parser.add_argument('--limit', type=int, default=10)
add_types_to_subparser(recent_parser, False)
recent_parser.set_defaults(func=recently_added)

list_parser = subparsers.add_parser('list')
list_parser.add_argument('--format', default='table', choices=['table', 'titles'])
list_parser.add_argument('--no-pager', action='store_false', dest='pager')
list_parser.add_argument('--order')
list_parser.add_argument('--todo', '--not-removed', action='store_true')
add_types_to_subparser(list_parser)
add_genre_to_subparser(list_parser)
add_reason_to_subparser(list_parser)
#TODO add sort opt
#list_parser.add_argument('--sort', )
list_parser.set_defaults(func=list_media)

priority_parser = subparsers.add_parser('top', aliases=['priority'])
add_types_to_subparser(priority_parser, False)
priority_parser.set_defaults(func=top_media)

started_parser = subparsers.add_parser('started')
add_types_to_subparser(started_parser, False)
started_parser.set_defaults(func=started_media)

argcomplete.autocomplete(parser)
args = parser.parse_args()
#print(args)
args.func(args)
