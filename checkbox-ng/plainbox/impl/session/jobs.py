# This file is part of Checkbox.
#
# Copyright 2012-2015 Canonical Ltd.
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
"""
:mod:`plainbox.impl.session.jobs` -- jobs state handling
========================================================

This module contains a helper class for associating job state within a
particular session. The :class:`JobState` class holds references to a
:class:`JobDefinition` and :class:`JobResult` as well as a list of inhibitors
that prevent the job from being runnable in a particular session.
"""

import logging

from plainbox.abc import IJobResult
from plainbox.i18n import gettext as _
from plainbox.impl import pod
from plainbox.impl.resource import ResourceExpression
from plainbox.impl.result import MemoryJobResult
from plainbox.impl.unit.job import JobDefinition

logger = logging.getLogger("plainbox.session.jobs")


class JobReadinessInhibitor(pod.POD):
    """
    Class representing the cause of a job not being ready to execute.

    It is intended to be consumed by UI layers and to provide them with enough
    information to render informative error messages or other visual feedback
    that will aid the user in understanding why a job cannot be started.

    There are four possible not ready causes:

        UNDESIRED:
            This job was not selected to run in this session

        PENDING_DEP:
           This job depends on another job which was not started yet

        FAILED_DEP:
            This job depends on another job which was started and failed

        PENDING_RESOURCE:
            This job has a resource requirement expression that uses a resource
            produced by another job which was not started yet

        FAILED_RESOURCE:
            This job has a resource requirement that evaluated to a false value

    All causes apart from UNDESIRED use the related_job property to encode a
    job that is related to the problem. The PENDING_RESOURCE and
    FAILED_RESOURCE causes also store related_expression that describes the
    relevant requirement expression.

    There are three attributes that can be accessed:

        cause:
            Encodes the reason why a job is not ready, see above.

        related_job:
            Provides additional context for the problem. This is not the job
            that is affected, rather, the job that is causing the problem.

        related_expression:
            Provides additional context for the problem caused by a failing
            resource expression.
    """
    # XXX: PENDING_RESOURCE is not strict, there are multiple states that are
    # clumped here which is something I don't like. A resource may be still
    # "pending" as in PENDING_DEP (it has not ran yet) or it could have ran but
    # failed to produce any data, it could also be prevented from running
    # because it has unmet dependencies. In essence it tells us nothing about
    # if related_job.can_start() is true or not.
    #
    # XXX: FAILED_RESOURCE is "correct" but somehow misleading, FAILED_RESOURCE
    # is used to represent a resource expression that evaluated to a non-True
    # value

    UNDESIRED, PENDING_DEP, FAILED_DEP, PENDING_RESOURCE, FAILED_RESOURCE \
        = range(5)

    _cause_display = {
        UNDESIRED: "UNDESIRED",
        PENDING_DEP: "PENDING_DEP",
        FAILED_DEP: "FAILED_DEP",
        PENDING_RESOURCE: "PENDING_RESOURCE",
        FAILED_RESOURCE: "FAILED_RESOURCE"
    }

    cause = pod.Field(
        doc="cause (constant) of the inhibitor",
        type=int,
        initial=pod.MANDATORY,
        assign_filter_list=[pod.read_only_assign_filter])

    related_job = pod.Field(
        doc="an (optional) job reference",
        type=JobDefinition,
        assign_filter_list=[pod.read_only_assign_filter])

    related_expression = pod.Field(
        doc="an (optional) resource expression reference",
        type=ResourceExpression,
        assign_filter_list=[pod.read_only_assign_filter])

    def __init__(self, cause, related_job=None, related_expression=None):
        """
        Initialize a new inhibitor with the specified cause.

        If cause is other than UNDESIRED a related_job is necessary. If cause
        is either PENDING_RESOURCE or FAILED_RESOURCE related_expression is
        necessary as well. A ValueError is raised when this is violated.
        """
        if cause not in self._cause_display:
            raise ValueError(_("unsupported value for cause"))
        if cause != self.UNDESIRED and related_job is None:
            raise ValueError(
                # TRANSLATORS: please don't translate related_job, None and
                # cause
                _("related_job must not be None when cause is {}").format(
                    self._cause_display[cause]))
        if cause in (self.PENDING_RESOURCE, self.FAILED_RESOURCE) \
                and related_expression is None:
            raise ValueError(_(
                # TRANSLATORS: please don't translate related_expression, None
                # and cause.
                "related_expression must not be None when cause is {}"
            ).format(self._cause_display[cause]))
        return super().__init__(cause, related_job, related_expression)

    @property
    def cause_name(self):
        return self._cause_display[self.cause]

    def __repr__(self):
        return "<{} cause:{} related_job:{!r} related_expression:{!r}>".format(
            self.__class__.__name__, self._cause_display[self.cause],
            self.related_job, self.related_expression)

    def __str__(self):
        if self.cause == self.UNDESIRED:
            # TRANSLATORS: as in undesired job
            return _("undesired")
        elif self.cause == self.PENDING_DEP:
            return _("required dependency {!r} did not run yet").format(
                self.related_job.id)
        elif self.cause == self.FAILED_DEP:
            return _("required dependency {!r} has failed").format(
                self.related_job.id)
        elif self.cause == self.PENDING_RESOURCE:
            return _(
                "resource expression {!r} could not be evaluated because"
                " the resource it depends on did not run yet"
            ).format(self.related_expression.text)
        else:
            assert self.cause == self.FAILED_RESOURCE
            return _("resource expression {!r} evaluates to false").format(
                self.related_expression.text)


# A global instance of :class:`JobReadinessInhibitor` with the UNDESIRED cause.
# This is used a lot and it makes no sense to instantiate all the time.
UndesiredJobReadinessInhibitor = JobReadinessInhibitor(
    JobReadinessInhibitor.UNDESIRED)


JOB_VALUE = object()


class OverridableJobField(pod.Field):
    """
    A readable-writable field that has a special initial value ``JOB_VALUE``
    which is interpreted as "load this value from the corresponding job
    definition".

    This field class facilitates implementation of fields that have some
    per-job value but can be also overridden in a session state context.
    """

    def __init__(self, job_field, doc=None, type=None, notify=False,
                 assign_filter_list=None):
        super().__init__(
            doc, type, JOB_VALUE, None, notify, assign_filter_list)
        self.job_field = job_field

    def __get__(self, instance, owner):
        value = super().__get__(instance, owner)
        if value is JOB_VALUE:
            return getattr(instance.job, self.job_field)
        else:
            return value


def job_assign_filter(instance, field, old_value, new_value):
    # FIXME: This setter should not exist. job attribute should be
    # read-only. This is a temporary kludge to get session restoring
    # over DBus working. Once a solution that doesn't involve setting
    # a JobState's job attribute is implemented, please remove this
    # awful method.
    return new_value


def job_via_assign_filter(instance, field, old_value, new_value):
    if old_value is not pod.UNSET and not isinstance(new_value, JobDefinition):
        raise TypeError("via_job must be the actual job, not the checksum")
    return new_value


class JobState(pod.POD):
    """
    Class representing the state of a job in a session.

    Contains the following basic properties of each job:

        * the readiness_inhibitor_list that prevent the job form starting
        * the result (outcome) of the run (IJobResult)
        * the effective category identifier
        * the job that was used to create it (via_job)

    For convenience (to SessionState implementation) it also has a reference to
    the job itself.  This class is a pure state holder an will typically
    collaborate with the SessionState class and the UI layer.
    """

    job = pod.Field(
        doc="the job associated with this state",
        type=JobDefinition,
        initial=pod.MANDATORY,
        assign_filter_list=[job_assign_filter])

    readiness_inhibitor_list = pod.Field(
        doc="the list of readiness inhibitors of the associated job",
        type="List[JobReadinessInhibitor]",
        initial_fn=lambda: [UndesiredJobReadinessInhibitor])

    result = pod.Field(
        doc="the result of running the associated job",
        type=IJobResult,
        initial_fn=lambda: MemoryJobResult({}),
        notify=True)

    via_job = pod.Field(
        doc="the parent job definition",
        type=JobDefinition,
        assign_filter_list=[job_via_assign_filter])

    effective_category_id = OverridableJobField(
        job_field="category_id",
        doc="the effective categorization of this test in a session",
        type=str)

    def can_start(self):
        """
        Quickly check if the associated job can run right now.
        """
        return len(self.readiness_inhibitor_list) == 0

    def get_readiness_description(self):
        """
        Get a human readable description of the current readiness state
        """
        if self.readiness_inhibitor_list:
            return _("job cannot be started: {}").format(
                ", ".join((str(inhibitor)
                           for inhibitor in self.readiness_inhibitor_list)))
        else:
            return _("job can be started")
