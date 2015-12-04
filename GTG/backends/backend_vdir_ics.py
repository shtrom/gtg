# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Getting Things GNOME! - a personal organizer for the GNOME desktop
# Copyright (c) 2008-2013 - Lionel Dricot & Bertrand Rousseau
# Copyright (c) 2015 - Olivier Mehani (this file)
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program.  If not, see <http://www.gnu.org/licenses/>.
# -----------------------------------------------------------------------------

'''
Localfile is a read/write backend that will store your tasks as VTODO ICS files
in a vdir [0]. The idea is to use this backend with a remote CalDAV server
synced locally with vdirsyncer [1]. This allows to use GTG alongside CLI
clients such at todoman [2].

[0] https://vdirsyncer.readthedocs.org/en/stable/vdir.html
[1] https://vdirsyncer.readthedocs.org/
[2] https://hugo.barrera.io/journal/2015/03/30/introducing-todoman/
'''

import os

import datetime
# from datetime import datetime, date
from icalendar import Calendar, Todo, vDate, vDatetime, vText

from GTG.backends.backendsignals import BackendSignals
from GTG.backends.genericbackend import GenericBackend
from GTG.core.dirs import DATA_DIR
from GTG.core.translations import _
from GTG.core.task import Task
from GTG.tools.dates import Date
from GTG.tools.logger import Log

def vDateMaybeTime(date):
    if type(date) is datetime.date:
        return vDate(date)
    elif type(date) is datetime.datetime:
        return vDatetime(date)
    elif type(date) is Date:
        if date == Date.no_date():
            return None
        else:
            return vDateMaybeTime(date.date())
    raise TypeError('%s is neither datetime.date or datetime.datetime' % (type(date)))

class Backend(GenericBackend):
    """
    Localfile backend, which stores your tasks in a XML file in the standard
    XDG_DATA_DIR/gtg folder (the path is configurable).
    An instance of this class is used as the default backend for GTG.
    This backend loads all the tasks stored in the localfile after it's enabled
    and from that point on just writes the changes to the file: it does not
    listen for eventual file changes
    """

    _general_description = {
        GenericBackend.BACKEND_NAME: "backend_vdir_ics",
        GenericBackend.BACKEND_HUMAN_NAME: _("vdir ICS"),
        GenericBackend.BACKEND_AUTHORS: ["Olivier Mehani"],
        GenericBackend.BACKEND_TYPE: GenericBackend.TYPE_READWRITE,
        GenericBackend.BACKEND_DESCRIPTION:
        _("Your tasks are saved in a vdir (ICS format). " +
          "This stores tasks as ICS VTODO files in a vdir " +
          "folder, which allows external syncing with CalDAV " +
          "(e.g., with vdirsyncer) and interation with other " +
          "tools such as todoman."),
    }

    # Here, we define a parameter "vdir", which is a string, and has a default
    # value as a random file in the default path
    _static_parameters = {
        "path": {
            GenericBackend.PARAM_TYPE: GenericBackend.TYPE_STRING,
            GenericBackend.PARAM_DEFAULT_VALUE:
            os.path.expanduser("~/.calendars/")}}

    # Map VTODO statuses to GTG's. There is no way to distinguish between
    # IN-PROGRESS and NEEDS-ACTION. This backend defaults to the latter, but
    # only updates existing tasks if the status has indeed been changed so as
    # not to overwrite information that other clients might rely on.
    _status_map = {
            "COMPLETED": Task.STA_DONE,
            "CANCELLED": Task.STA_DISMISSED,
            "IN-PROGRESS": Task.STA_ACTIVE,
            "NEEDS-ACTION": Task.STA_ACTIVE,
            "": None,
            }

    def __init__(self, parameters):
        """
        Instantiates a new backend.

        @param parameters: A dictionary of parameters, generated from
        _static_parameters. A few parameters are added to those, the list of
        these is in the "DefaultBackend" class, look for the KEY_* constants.

        The backend should take care if one expected value is None or
        does not exist in the dictionary.
        """
        super().__init__(parameters)

    def get_path(self):
        """
        Return the current path to vdir
        """
        path = self._parameters["path"]
        if os.sep not in path:
            # This is local path, convert it to absolute path
            path = os.path.join(DATA_DIR, path)
        return os.path.abspath(path)

    def initialize(self):
        """ This is called when a backend is enabled """
        super(Backend, self).initialize()

    def make_uid(self, tid):
        return "%s-%s-%s@gtg" % (datetime.datetime.now().strftime("%Y%m%dT%H%M%S%z"),
                tid, os.uname().nodename)

    def ics_file(self, rid):
        return os.path.join(self.get_path(), "%s.%s" % (rid, "ics"))

    def start_get_tasks(self):
        """ This function starts submitting the tasks from the vdir into
        GTG core. It's run as a separate thread.

        @return: start_get_tasks() might not return or finish
        """
        self._get_tasks_from_path(self.get_path())

    def _get_tasks_from_path(self, path):
        for child in os.listdir(path):
            if child[-4:] == ".ics":
                file = open(os.path.join(path, child))
                data = file.read()
                file.close()
                if data.find("\nBEGIN:VTODO\n"):
                    Log.debug("GTG <- %s: %s %s" %(self._general_description[self.BACKEND_HUMAN_NAME],
                        path, child))
                    cal = Calendar.from_ical(data)
                    # XXX: this will probably create weird things if there are
                    # more than one VTODO per ICS file
                    for todo in cal.walk("VTODO"):
                        task = self.task_from_vtodo(todo)
                        self.datastore.push_task(task)

    def task_from_vtodo(self, todo):
        """ This function create a new Task in the GTG core based on the
        contents of the Todo
        
        @return: a new Task to push into self.datastore if needed
        """
        tid = todo['uid']
        task = self.datastore.task_factory(tid)
        task.add_remote_id(self._general_description[GenericBackend.BACKEND_NAME], tid)
        task.set_title(todo['SUMMARY'])

        status = task.STA_ACTIVE
        donedate = None
        if todo.has_key('STATUS'):
            status = self._status_map[todo['STATUS']]
            if status == task.STA_DONE:
                donedate = Date(todo["COMPLETED"].dt)
        task.set_status(status, donedate=donedate)

        if todo.has_key("DUE"):
            duedate = Date(todo["DUE"].dt)
            task.set_due_date(duedate)

        if todo.has_key("DTSTART"):
            startdate = Date(todo["DTSTART"].dt)
            task.set_start_date(startdate)

        # if todo.has_key("LAST-MODIFIED"):
        #     modified = Date(todo["LAST-MODIFIED"].dt)
        #     task.set_start_date(modified)

        if todo.has_key("CATEGORIES"):
            tags = todo.get_inline(["CATEGORIES"])
            # XXX: actively ignore languageparam after ';', see [0]
            # [0] https://tools.ietf.org/html/rfc2445#page-78
            # tags = (tag for tag in tags.split(',') if tag.strip() != "")
            task.tag_added(tags)

        if todo.has_key("DESCRIPTION"):
            content = todo["DESCRIPTION"]
            # parse subtasks
            #  find subtask ID by summary
            task.set_text(content)

        if todo.has_key("RELATED-TO"):
            subtasks = todo.get_inline(["RELATED-TO"])
            # FIXME: default relationship is PARENT, we treat it as a CHILD here
            # It can also be overriden with a reltypeparam [1]
            # [1] https://tools.ietf.org/html/rfc2445#page-110
            # subtasks = (subtask for subtask in subtasks.split(',')
            # 		if subtask.strip() != "")
            for subtask in subtasks:
                task.add_child(subtask)

        return task

    def task_to_vtodo(self, task, todo=None):
        vnow = vDateMaybeTime(datetime.datetime.now())
        if todo is None:
            todo = Todo()
            todo['CREATED'] = vnow

        todo['UID'] = task.get_remote_ids()[self._general_description[GenericBackend.BACKEND_NAME]]
        todo['SUMMARY'] = vText(task.get_title())

        status = task.get_status()
        if not todo.has_key('STATUS') or status != self._status_map[todo['STATUS']]:
            # Only update the VTODO if the mapped status is different
            if status == task.STA_DONE:
            	todo['STATUS'] = 'COMPLETED'
            elif status == task.STA_DISMISSED:
            	todo['STATUS'] = 'CANCELLED'
            else:
            	# GTG can't distinguish 'NEEDS-ACTION' from 'IN-PROGRESS'
            	todo['STATUS'] = 'NEEDS-ACTION'
		# Update the completion date separately in case it has changed
        if status == task.STA_DONE and \
                (not todo.has_key('COMPLETED')): # or
                        #Date(todo['COMPLETED']).days_left(task.get_closed_date().isoformat()) != 0 ):
            todo['COMPLETED'] = vDateMaybeTime(task.get_closed_date())

        todo['DUE'] = vDateMaybeTime(task.get_due_date())
        # Remove empty dates; this allows updating tasks when the date has been removed
        if todo['DUE'] is None:
            del todo['DUE']

        todo['DTSTART'] = vDateMaybeTime(task.get_start_date())
        if todo['DTSTART'] is None:
            del todo['DTSTART']

        todo['LAST-MODIFIED'] = vnow
        if todo['LAST-MODIFIED'] is None:
            del todo['LAST-MODIFIED']

        tags = task.get_tags()
        if len(tags) > 0:
            todo.set_inline('CATEGORIES', [tag.get_name().strip('@') for tag in tags])

        # XXX: remove <content>
        todo['DESCRIPTION'] = vText(task.get_text())

        subtasks = task.get_children()
        if len(subtasks) > 0:
            todo.set_inline('RELATED-TO', subtasks)

        return todo

    def set_task(self, task):
        """
        This function is called from GTG core whenever a task should be
        saved, either because it's a new one or it has been modified.
        This function will look into the load or create an ICS file,
        and convert the task data.

        @param task: the task object to save

        XXX: This doesn't support multiple VTODOs in a single ICS file.
        It will create one file per task, even if it already exists in anothe one.
        """
        tid = task.get_id()
        rids = task.get_remote_ids()
        if self._general_description[GenericBackend.BACKEND_NAME] in rids.keys():
                rid = rids[self._general_description[GenericBackend.BACKEND_NAME]]
        else:
                rid = self.make_uid(tid)
                task.add_remote_id(self._general_description[GenericBackend.BACKEND_NAME], rid)
        ics_file = self.ics_file(rid)

        Log.debug("GTG -> %s: %s" % (self._general_description[self.BACKEND_HUMAN_NAME], ics_file))

        if os.path.exists(ics_file):
                file = open(ics_file)
                data = file.read()
                file.close()
                cal = Calendar.from_ical(data)
                # todo = [t in cal.walk('VTODO') where t['UID'] == tid]
                # todo = todo.pop()
                todo = cal.walk('VTODO')[0]
                # XXX: Assume there is only one VTODO, clear the rest
                cal.subcomponents.clear()
        else:
                cal = Calendar()
                cal.add("prodid", "//GTG//vdir ICS//EN")
                cal.add('version', '2.0')
                todo = None

        todo = self.task_to_vtodo(task, todo)
        cal.add_component(todo)

        f = open(ics_file, 'wb')
        f.write(cal.to_ical())
        f.close()

    def remove_task(self, tid):
        """ This function is called from GTG core whenever a task must be
        removed from the backend. Note that the task could be not present here.

        @param tid: the id of the task to delete
        """
        # XXX: remove related-to tags to this task?
        os.remove(self.ics_file(tid))

    def on_continue_clicked(self, *args):
        """ Callback when the user clicks continue in the infobar
        """
        pass
