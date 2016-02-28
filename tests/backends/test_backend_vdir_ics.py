# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Getting Things GNOME! - a personal organizer for the GNOME desktop
# Copyright (c) 2008-2015 - Lionel Dricot & Bertrand Rousseau
# Copyright (c) 2016 - Olivier Mehani (this file)
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

import unittest
from unittest.mock import patch, mock_open, Mock

import logging
from icalendar import Calendar, Todo, vDate, vDatetime, vText

from liblarch import MainTree

from GTG.core.tag import Tag
from GTG.core.task import Task
from GTG.tools.dates import Date
from GTG.tools.logger import Log

from GTG.backends.backend_vdir_ics import Backend, vDateMaybeTime

class TestConversion(unittest.TestCase):
    def setUp(self):
        # Log.setLevel(logging.INFO)
        self.mock_requester = patch('GTG.core.requester.Requester').start()
        self.mock_requester.get_tag = lambda x: Tag(x, self.mock_requester)
        self.mock_requester.get_task = lambda x: self.task_tree.get_node(x)

        self.task = Task("test_conversion_task", self.mock_requester)
        self.task.set_complex_title("Test vDir ICS backend @coding @testing defer:soon due:someday")
        self.task.set_text("testing")

        self.task_tree = MainTree()
        self.task_tree.add_node(self.task)

    def tearDown(self):
        patch.stopall()


    def test_1_populate_vtodo(self):
        # Task -> VTODO
        todo = Todo()
        Backend._populate_vtodo(todo, self.task)
        self.assertEqual(todo['UID'], Backend._make_uid(self.task.get_id()))
        self.assertEqual(todo['SUMMARY'], self.task.get_title())
        self.assertEqual("<content>%s</content>" % (todo['DESCRIPTION']), self.task.get_text())
        self.assertEqual(Backend._status_map[todo['STATUS']], self.task.get_status())
        self._test_vtodo_date(todo, 'DTSTART', self.task.get_start_date())
        self.assertTrue(Backend._fuzzy_key % ("DTSTART", "soon") in todo["CATEGORIES"])
        self._test_vtodo_date(todo, 'DUE', self.task.get_due_date())
        self._test_vtodo_date(todo, 'COMPLETED', self.task.get_closed_date())

        self.assertListEqual(
                [t.get_name().strip("@") for t in self.task.get_tags()], # task tags
                [t for t in todo.get_inline('CATEGORIES', decode=False)  # todo tags without GTG:*
                    if not t.startswith(Backend._fuzzy_key[0:3])])

        print(todo.to_ical().decode())

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


    def test_2_populate_task(self):
        todo = Todo()
        Backend._populate_vtodo(todo, self.task)
        # VTODO -> Task
        task2 = Task("test_2_populate_task", self.mock_requester)
        Backend._populate_task(task2, todo)
        rids = self.task.get_remote_ids()
        self.assertTrue(Backend.get_name() in rids.keys())
        rid = rids[Backend.get_name()]
        self.assertEqual(rid, todo['UID'])
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


    def test_3_task_relationships_to_vtodo(self):
        parent = Task("test_conversion_parent", self.mock_requester)
        parent.set_complex_title("this is a parent")

        self.task_tree.add_node(parent)

        parent.add_child(self.task.get_id())
        self.assertTrue(self.task.has_parent())

        todo = Todo()
        ptodo = Todo()
        # In this order, this also tests the ID generation for parents
        Backend._populate_vtodo(todo, self.task)
        Backend._populate_vtodo(ptodo, parent)

        print(todo.to_ical().decode())
        print(ptodo.to_ical().decode())

        self.assertTrue("RELATED-TO" in todo.keys())
        self.assertTrue(
                ("<%s>" % (ptodo['UID'])).encode() in
                    todo.get_inline("RELATED-TO")
                )

        # Informational, but let's test for it anyway
        self.assertTrue("RELATED-TO;RELTYPE=CHILD" in ptodo.keys())
        self.assertTrue(
                ("<%s>" % (todo['UID'])).encode() in
                    ptodo.get_inline("RELATED-TO;RELTYPE=CHILD")
                )


    @unittest.skip("issue with the requester not being fully implemented")
    def test_4_task_relationships_to_task(self):
        self.fail("test conversion from VTODOs with relations to Task")

        self.fail() # XXX: useful if we want to see the output


    @unittest.skip("not implemented")
    def test_5_statuses(self):
        self.fail("test close/dismiss")


    @unittest.skip("not implemented")
    def test_6_dates(self):
        self.fail("test normal date on due date")

if __name__ == '__main__':
    unittest.main(verbosity=2)
