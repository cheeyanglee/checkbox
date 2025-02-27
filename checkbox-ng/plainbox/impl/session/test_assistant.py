# This file is part of Checkbox.
#
# Copyright 2015 Canonical Ltd.
# Written by:
#   Zygmunt Krynicki <zygmunt.krynicki@canonical.com>
#
# Checkbox is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3,
# as published by the Free Software Foundation.

#
# Checkbox is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Checkbox.  If not, see <http://www.gnu.org/licenses/>.

"""Tests for the session assistant module class."""

from unittest import mock

from plainbox.impl.secure.providers.v1 import Provider1
from plainbox.impl.session.assistant import (
    SessionAssistant,
    UsageExpectation,
    SessionMetaData,
)
from plainbox.vendor import morris


@mock.patch("plainbox.impl.session.assistant.get_providers")
class SessionAssistantTests(morris.SignalTestCase):

    """Tests for the SessionAssitant class."""

    APP_ID = "app-id"
    APP_VERSION = "1.0"
    API_VERSION = "0.99"
    API_FLAGS = []

    def setUp(self):
        """Common set-up code."""
        self.sa = SessionAssistant(
            self.APP_ID, self.APP_VERSION, self.API_VERSION, self.API_FLAGS
        )
        # Monitor the provider_selected signal since some tests check it
        self.watchSignal(self.sa.provider_selected)
        # Create a few mocked providers that tests can use.
        # The all-important plainbox provider
        self.p1 = mock.Mock(spec_set=Provider1, name="p1")
        self.p1.namespace = "com.canonical.plainbox"
        self.p1.name = "com.canonical.plainbox:special"
        # An example 3rd party provider
        self.p2 = mock.Mock(spec_set=Provider1, name="p2")
        self.p2.namespace = "pl.zygoon"
        self.p2.name = "pl.zygoon:example"
        # A Canonical certification provider
        self.p3 = mock.Mock(spec_set=Provider1, name="p3")
        self.p3.namespace = "com.canonical.certification"
        self.p3.name = "com.canonical.certification:stuff"

    def _get_mock_providers(self):
        """Get some mocked provides for testing."""
        return [self.p1, self.p2, self.p3]

    def test_expected_call_sequence(self, mock_get_providers):
        """Track the sequence of allowed method calls."""
        mock_get_providers.return_value = self._get_mock_providers()
        # SessionAssistant.start_new_session() must now be allowed
        self.assertIn(
            self.sa.start_new_session,
            UsageExpectation.of(self.sa).allowed_calls,
        )

        # patch system_information to avoid the actual collection of
        # system_information in tests
        with mock.patch(
            "plainbox.impl.session.state.SessionState.system_information"
        ):
            # Call SessionAssistant.start_new_session()
            self.sa.start_new_session("just for testing")

        # SessionAssistant.start_new_session() must no longer allowed
        self.assertNotIn(
            self.sa.start_new_session,
            UsageExpectation.of(self.sa).allowed_calls,
        )
        # SessionAssistant.select_test_plan() must now be allowed
        self.assertIn(
            self.sa.select_test_plan,
            UsageExpectation.of(self.sa).allowed_calls,
        )
        # Use the manager to tidy up after the tests when normally you wouldnt
        # be allowed to
        self.sa._manager.destroy()

    @mock.patch(
        "plainbox.impl.session.assistant.UsageExpectation",
        new=mock.MagicMock(),
    )
    @mock.patch("plainbox.impl.session.assistant._logger")
    def test_finalize_session_incomplete(
        self, logger_mock, mock_get_providers
    ):
        self_mock = mock.MagicMock()
        self_mock._metadata.flags = [SessionMetaData.FLAG_INCOMPLETE]

        SessionAssistant.finalize_session(self_mock)

        self.assertNotIn(
            SessionMetaData.FLAG_INCOMPLETE, self_mock._metadata.flags
        )

    @mock.patch(
        "plainbox.impl.session.assistant.UsageExpectation",
        new=mock.MagicMock(),
    )
    @mock.patch("plainbox.impl.session.assistant._logger")
    def test_finalize_session_bootstrapping(
        self, logger_mock, mock_get_providers
    ):
        self_mock = mock.MagicMock()
        self_mock._metadata.flags = [SessionMetaData.FLAG_BOOTSTRAPPING]

        SessionAssistant.finalize_session(self_mock)

        self.assertNotIn(
            SessionMetaData.FLAG_BOOTSTRAPPING, self_mock._metadata.flags
        )

    @mock.patch("plainbox.impl.session.assistant.WellKnownDirsHelper")
    def test_delete_sessions(self, mock_well_known_dirs_helper, _):
        wkdh = mock_well_known_dirs_helper

        mock_storage_deleted = mock.MagicMock()
        mock_storage_deleted.id = 1

        mock_storage_not_deleted = mock.MagicMock()
        mock_storage_not_deleted.id = 2

        wkdh.get_storage_list.return_value = [
            mock_storage_deleted,
            mock_storage_not_deleted,
        ]

        SessionAssistant.delete_sessions(mock.MagicMock(), [1])

        self.assertTrue(mock_storage_deleted.remove.called)
        self.assertFalse(mock_storage_not_deleted.remove.called)

    def test_note_metadata_starting_job(self, _):
        self_mock = mock.MagicMock()

        SessionAssistant.note_metadata_starting_job(
            self_mock, {"id": 123}, mock.MagicMock()
        )

        self.assertTrue(self_mock._manager.checkpoint.called)
