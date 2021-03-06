from typing import Union

from flexmock import flexmock
from ogr.abstract import GitProject, GitService, CommitStatus
from packit.api import PackitAPI
from packit.config import PackageConfig, JobConfig, JobType, JobConfigTriggerType
from packit.exceptions import FailedCreateSRPM

from packit_service import sentry_integration
from packit_service.config import ServiceConfig
from packit_service.models import CoprBuild, SRPMBuild
from packit_service.service.events import (
    PullRequestEvent,
    PullRequestCommentEvent,
    CoprBuildEvent,
    PushGitHubEvent,
    ReleaseEvent,
)
from packit_service.service.models import CoprBuild as RedisCoprBuild
from packit_service.worker.build.copr_build import CoprBuildJobHelper
from packit_service.worker.reporting import StatusReporter


class FakeCoprBuildModel:
    build_id = 0

    def save(self):
        pass

    def add_build(self):
        pass


def build_helper(
    event: Union[
        PullRequestEvent,
        PullRequestCommentEvent,
        CoprBuildEvent,
        PushGitHubEvent,
        ReleaseEvent,
    ],
    metadata=None,
    trigger=None,
    jobs=None,
):
    if not metadata:
        metadata = {
            "owner": "nobody",
            "targets": [
                "fedora-29-x86_64",
                "fedora-30-x86_64",
                "fedora-31-x86_64",
                "fedora-rawhide-x86_64",
            ],
        }
    jobs = jobs or []
    jobs.append(
        JobConfig(
            type=JobType.copr_build,
            trigger=trigger or JobConfigTriggerType.pull_request,
            metadata=metadata,
        )
    )
    pkg_conf = PackageConfig(jobs=jobs, downstream_package_name="dummy")
    handler = CoprBuildJobHelper(
        config=ServiceConfig(),
        package_config=pkg_conf,
        project=GitProject("", GitService(), ""),
        event=event,
    )
    handler._api = PackitAPI(ServiceConfig(), pkg_conf)
    return handler


def test_copr_build_check_names(pull_request_event):
    helper = build_helper(
        event=pull_request_event,
        metadata={"owner": "nobody", "targets": ["bright-future-x86_64"]},
    )
    flexmock(StatusReporter).should_receive("set_status").with_args(
        state=CommitStatus.pending,
        description="Building SRPM ...",
        check_name="packit-stg/rpm-build-bright-future-x86_64",
        url="",
    ).and_return()
    flexmock(StatusReporter).should_receive("set_status").with_args(
        state=CommitStatus.pending,
        description="Building RPM ...",
        check_name="packit-stg/rpm-build-bright-future-x86_64",
        url="https://localhost:5000/copr-build/1/logs",
    ).and_return()

    flexmock(GitProject).should_receive("set_commit_status").and_return().never()
    flexmock(RedisCoprBuild).should_receive("create").and_return(FakeCoprBuildModel())
    flexmock(SRPMBuild).should_receive("create").and_return(SRPMBuild())
    flexmock(CoprBuild).should_receive("get_or_create").and_return(CoprBuild(id=1))
    flexmock(PackitAPI).should_receive("run_copr_build").and_return(1, None)
    assert helper.run_copr_build()["success"]


def test_copr_build_success_set_test_check(pull_request_event):
    # status is set for each build-target (4x):
    #  - Building SRPM ...
    #  - Building RPM ...
    # status is set for each test-target (4x):
    #  - Building SRPM ...
    #  - Building RPM ...
    test_job = JobConfig(
        type=JobType.tests, trigger=JobConfigTriggerType.pull_request, metadata={}
    )
    helper = build_helper(jobs=[test_job], event=pull_request_event)
    flexmock(GitProject).should_receive("set_commit_status").and_return().times(16)
    flexmock(RedisCoprBuild).should_receive("create").and_return(FakeCoprBuildModel())
    flexmock(SRPMBuild).should_receive("create").and_return(SRPMBuild())
    flexmock(CoprBuild).should_receive("get_or_create").and_return(CoprBuild(id=1))
    flexmock(PackitAPI).should_receive("run_copr_build").and_return(1, None).once()
    assert helper.run_copr_build()["success"]


def test_copr_build_for_branch(branch_push_event):
    # status is set for each build-target (4x):
    #  - Building SRPM ...
    #  - Building RPM ...
    branch_build_job = JobConfig(
        type=JobType.build,
        trigger=JobConfigTriggerType.commit,
        metadata={
            "branch": "build-branch",
            "owner": "nobody",
            "targets": [
                "fedora-29-x86_64",
                "fedora-30-x86_64",
                "fedora-31-x86_64",
                "fedora-rawhide-x86_64",
            ],
        },
    )
    helper = build_helper(jobs=[branch_build_job], event=branch_push_event)
    flexmock(GitProject).should_receive("set_commit_status").and_return().times(8)
    flexmock(RedisCoprBuild).should_receive("create").and_return(FakeCoprBuildModel())
    flexmock(SRPMBuild).should_receive("create").and_return(SRPMBuild())
    flexmock(CoprBuild).should_receive("get_or_create").and_return(CoprBuild(id=1))
    flexmock(PackitAPI).should_receive("run_copr_build").and_return(1, None).once()
    assert helper.run_copr_build()["success"]


def test_copr_build_for_release(release_event):
    # status is set for each build-target (4x):
    #  - Building SRPM ...
    #  - Building RPM ...
    branch_build_job = JobConfig(
        type=JobType.build,
        trigger=JobConfigTriggerType.release,
        metadata={
            "branch": "build-branch",
            "owner": "nobody",
            "targets": [
                "fedora-29-x86_64",
                "fedora-30-x86_64",
                "fedora-31-x86_64",
                "fedora-rawhide-x86_64",
            ],
        },
    )
    helper = build_helper(jobs=[branch_build_job], event=release_event)
    flexmock(GitProject).should_receive("set_commit_status").and_return().times(8)
    flexmock(RedisCoprBuild).should_receive("create").and_return(FakeCoprBuildModel())
    flexmock(SRPMBuild).should_receive("create").and_return(SRPMBuild())
    flexmock(CoprBuild).should_receive("get_or_create").and_return(CoprBuild(id=1))
    flexmock(PackitAPI).should_receive("run_copr_build").and_return(1, None).once()
    assert helper.run_copr_build()["success"]


def test_copr_build_success(pull_request_event):
    # status is set for each build-target (4x):
    #  - Building SRPM ...
    #  - Building RPM ...
    helper = build_helper(event=pull_request_event)
    flexmock(GitProject).should_receive("set_commit_status").and_return().times(8)
    flexmock(RedisCoprBuild).should_receive("create").and_return(FakeCoprBuildModel())
    flexmock(SRPMBuild).should_receive("create").and_return(SRPMBuild())
    flexmock(CoprBuild).should_receive("get_or_create").and_return(CoprBuild(id=1))
    flexmock(PackitAPI).should_receive("run_copr_build").and_return(1, None).once()
    assert helper.run_copr_build()["success"]


def test_copr_build_fails_in_packit(pull_request_event):
    # status is set for each build-target (4x):
    #  - Building SRPM ...
    #  - Build failed, check latest comment for details.
    helper = build_helper(event=pull_request_event)
    templ = "packit-stg/rpm-build-fedora-{ver}-x86_64"
    for v in ["29", "30", "31", "rawhide"]:
        flexmock(GitProject).should_receive("set_commit_status").with_args(
            "528b803be6f93e19ca4130bf4976f2800a3004c4",
            CommitStatus.pending,
            "",
            "Building SRPM ...",
            templ.format(ver=v),
            trim=True,
        ).and_return().once()
    for v in ["29", "30", "31", "rawhide"]:
        flexmock(GitProject).should_receive("set_commit_status").with_args(
            "528b803be6f93e19ca4130bf4976f2800a3004c4",
            CommitStatus.failure,
            "https://localhost:5000/srpm-build/2/logs",
            "SRPM build failed, check the logs for details.",
            templ.format(ver=v),
            trim=True,
        ).and_return().once()
    flexmock(RedisCoprBuild).should_receive("create").and_return(FakeCoprBuildModel())
    flexmock(SRPMBuild).should_receive("create").and_return(SRPMBuild(id=2))
    flexmock(CoprBuild).should_receive("get_or_create").and_return(CoprBuild(id=1))
    flexmock(sentry_integration).should_receive("send_to_sentry").and_return().once()
    flexmock(PackitAPI).should_receive("run_copr_build").and_raise(
        FailedCreateSRPM, "some error"
    )
    assert not helper.run_copr_build()["success"]


def test_copr_build_no_targets(pull_request_event):
    # status is set for each build-target (fedora-stable => 2x):
    #  - Building SRPM ...
    #  - Building RPM ...
    helper = build_helper(event=pull_request_event, metadata={"owner": "nobody"})
    flexmock(GitProject).should_receive("set_commit_status").and_return().times(4)
    flexmock(RedisCoprBuild).should_receive("create").and_return(FakeCoprBuildModel())
    flexmock(SRPMBuild).should_receive("create").and_return(SRPMBuild())
    flexmock(CoprBuild).should_receive("get_or_create").and_return(CoprBuild(id=1))
    flexmock(PackitAPI).should_receive("run_copr_build").and_return(1, None).once()
    assert helper.run_copr_build()["success"]
