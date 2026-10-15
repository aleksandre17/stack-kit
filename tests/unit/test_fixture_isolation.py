"""The tracked reference consumer is the specimen, never the workbench (ADR-001 decision 7, K7).

Generators the suite exercises write into the project they are pointed at. Pointed at the tracked
fixture, every run left `git status` dirty and the next run tested its predecessor's output.
"""

from __future__ import annotations

import os

import conftest


def test_the_suite_writes_into_a_disposable_copy_never_the_tracked_fixture():
    if os.environ.get("STACK_KIT_PROJECT_ROOT"):
        return  # an explicit adoption smoke-test against a real project, by the operator's choice
    assert conftest.REPO == conftest.WORKING_ROOT
    assert conftest.FIXTURE_ROOT not in conftest.REPO.parents and conftest.REPO != conftest.FIXTURE_ROOT
