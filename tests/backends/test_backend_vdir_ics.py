# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Getting Things GNOME! - a personal organizer for the GNOME desktop
# Copyright (c) 2008-2015 - Lionel Dricot & Bertrand Rousseau
#& Copyright (c) 2016 - Olivier Mehani (this file)
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
#] this program.  If not, see <http://www.gnu.org/licenses/>.
# -----------------------------------------------------------------------------

from unittest import TestCase
from unittest.mock import patch, mock_open, Mock

from icalendar import Calendar, Todo, vDate, vDatetime, vText
from GTG.core.task import Task
from GTG.core.tag import Tag
from GTG.tools.dates import Date

from GTG.backends.backend_vdir_ics import Backend, vDateMaybeTime

class TestConversion(TestCase):
    def setUp(self):
        self.mock_requester = patch('GTG.core.requester.Requester').start()
        self.mock_requester.get_tag= lambda x: Tag(x, self.mock_requester)

        self.task = Task("test_conversion_task", self.mock_requester)
        self.task.set_complex_title("Test vDir ICS backend @coding @testing defer:soon due:someday")
        self.task.set_text("testing")

    def tearDown(self):
        patch.stopall()

    def test_populate_functions(self):
        todo = Todo()
        Backend._populate_vtodo(todo, self.task)
        self.assertEqual(todo['SUMMARY'], self.task.get_title())
        self.assertEqual(todo['DESCRIPTION'], self.task.get_text())
        self.assertEqual(Backend._status_map[todo['STATUS']], self.task.get_status())
        self._test_vtodo_date(todo, 'DTSTART', self.task.get_start_date())
        self.assertTrue(Backend._fuzzy_key % ("DTSTART", "soon") in todo["CATEGORIES"])
        self._test_vtodo_date(todo, 'DUE', self.task.get_due_date())
        self._test_vtodo_date(todo, 'COMPLETED', self.task.get_closed_date())

        self.assertListEqual(
                [t.get_name().strip("@") for t in self.task.get_tags()], # task tags
                [t for t in todo.get_inline('CATEGORIES', decode=False)  # todo tags without GTG:*
                    if not t.startswith(Backend._fuzzy_key[0:3])])

        # XXX: test relationships
        # XXX: test ids

        task2 = Task("", self.mock_requester)
        Backend._populate_task(task2, todo)
        self.assertEqual(task2.get_title(), self.task.get_title())
        self.assertEqual(task2.get_text(), self.task.get_text())
        self.assertEqual(task2.get_status(), self.task.get_status())
        self.assertEqual(task2.get_start_date(), self.task.get_start_date())
        self.assertEqual(task2.get_due_date(), self.task.get_due_date())
        self.assertEqual(task2.get_closed_date(), self.task.get_closed_date())

        self.assertListEqual(
                [t.get_name() for t in self.task.get_tags()],
                [t.get_name() for t in task2.get_tags()]
                )

        # self.fail()


    def _test_vtodo_date(self, todo, attribute, taskdate):
        if taskdate == Date.no_date():
            self.assertFalse(todo.has_key(attribute))
        else:
            self.assertTrue(todo.has_key(attribute))
            if taskdate == Date.soon():
                self.assertTrue(Backend._fuzzy_key % (attribute, "soon") in todo["CATEGORIES"])
            elif taskdate == Date.someday():
                self.assertTrue(Backend._fuzzy_key % (attribute, "someday") in todo["CATEGORIES"])
            else:
                self.assertEqual(todo[attribute].dt, taskdate)

if __name__ == '__main__':
    unittest.main(verbosity=2)
