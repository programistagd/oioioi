# coding: utf-8

import os.path
import urllib
import zipfile
from cStringIO import StringIO

from django.core.management.base import CommandError
from nose.plugins.attrib import attr
from nose.tools import nottest
from django.test.utils import override_settings
from django.test import TransactionTestCase
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.conf import settings

from oioioi.base.tests import TestCase
from oioioi.filetracker.tests import TestStreamingMixin
from oioioi.sinolpack.package import SinolPackageBackend, \
        DEFAULT_TIME_LIMIT, DEFAULT_MEMORY_LIMIT
from oioioi.contests.models import ProblemInstance, Contest, \
        Submission, UserResultForContest
from oioioi.contests.scores import IntegerScore
from oioioi.problems.models import Problem, ProblemStatement, ProblemPackage
from oioioi.programs.models import Test, OutputChecker, ModelSolution, \
        TestReport
from oioioi.sinolpack.models import ExtraConfig, ExtraFile
from oioioi.contests.current_contest import ContestMode


@nottest
def get_test_filename(name):
    return os.path.join(os.path.dirname(__file__), 'files', name)


BOTH_CONFIGURATIONS = '%test_both_configurations'


# When a class inheriting from django.test.TestCase is decorated with
# enable_both_unpack_configurations, all its methods decorated with
# both_configurations will be run twice. Once in safe and once in unsafe unpack
# mode.

# Unfortunately, you won't be able run such a decorated method as a single
# test, that is:
# ./test.sh oioioi.sinolpack.tests:TestSinolPackage.test_huge_unpack_update
# will NOT work.
@nottest
def enable_both_unpack_configurations(cls):
    for name, fn in cls.__dict__.items():
        if getattr(fn, BOTH_CONFIGURATIONS, False):
            setattr(cls, '%s_safe' % (name),
                    override_settings(USE_SINOLPACK_MAKEFILES=False)(fn))
            setattr(cls, '%s_unsafe' % (name),
                    override_settings(USE_SINOLPACK_MAKEFILES=True)(fn))
            delattr(cls, name)
    return cls


@nottest
def both_configurations(fn):
    setattr(fn, BOTH_CONFIGURATIONS, True)
    return fn


# Fixes error "no such table: nose_c" as described in
# https://github.com/jbalogh/django-nose/issues/15#issuecomment-1033686
Test._meta.get_all_related_objects()
TestReport._meta.get_all_related_objects()
ModelSolution._meta.get_all_related_objects()


@enable_both_unpack_configurations
class TestSinolPackage(TestCase):
    fixtures = ['test_users', 'test_contest']

    def test_identify_zip(self):
        filename = get_test_filename('test_simple_package.zip')
        self.assert_(SinolPackageBackend().identify(filename))

    def test_identify_tgz(self):
        filename = get_test_filename('test_full_package.tgz')
        self.assert_(SinolPackageBackend().identify(filename))

    def test_title_in_config_yml(self):
        filename = get_test_filename('test_simple_package.zip')
        call_command('addproblem', filename)
        problem = Problem.objects.get()
        self.assertEqual(problem.name, 'Testowe')

    def test_title_from_doc(self):
        filename = get_test_filename('test_simple_package_no_config.zip')
        call_command('addproblem', filename)
        problem = Problem.objects.get()
        self.assertNotEqual(problem.name, 'Not this one')
        self.assertEqual(problem.name, 'Testowe')

    def test_latin2_title(self):
        filename = get_test_filename('test_simple_package_latin2.zip')
        call_command('addproblem', filename)
        problem = Problem.objects.get()
        self.assertEqual(problem.name, u'Łąka')

    def test_utf8_title(self):
        filename = get_test_filename('test_simple_package_utf8.zip')
        call_command('addproblem', filename)
        problem = Problem.objects.get()
        self.assertEqual(problem.name, u'Łąka')

    def test_memory_limit_from_doc(self):
        filename = get_test_filename('test_simple_package_no_config.zip')
        call_command('addproblem', filename)
        test = Test.objects.filter(memory_limit=132000)
        self.assertEqual(test.count(), 5)

    def test_attachments(self):
        filename = get_test_filename('test_simple_package_attachments.zip')
        call_command('addproblem', filename)
        problem = Problem.objects.get()
        self.assertEqual(problem.attachments.all().count(), 1)

    def test_attachments_no_directory(self):
        filename = get_test_filename('test_simple_package.zip')
        call_command('addproblem', filename)
        problem = Problem.objects.get()
        self.assertEqual(problem.attachments.all().count(), 0)

    def test_attachments_empty_directory(self):
        filename = get_test_filename(
            'test_simple_package_attachments_empty.zip')
        call_command('addproblem', filename)
        problem = Problem.objects.get()
        self.assertEqual(problem.attachments.all().count(), 0)

    def test_attachments_reupload_same_attachments(self):
        filename = get_test_filename('test_simple_package_attachments.zip')
        call_command('addproblem', filename)
        problem = Problem.objects.get()

        filename = get_test_filename('test_simple_package_attachments.zip')
        call_command('updateproblem', str(problem.id), filename)
        problem = Problem.objects.get()
        self.assertEqual(problem.attachments.all().count(), 1)

    def test_attachments_reupload_no_attachments(self):
        filename = get_test_filename('test_simple_package_attachments.zip')
        call_command('addproblem', filename)
        problem = Problem.objects.get()

        filename = get_test_filename(
            'test_simple_package_attachments_empty.zip')
        call_command('updateproblem', str(problem.id), filename)
        problem = Problem.objects.get()
        self.assertEqual(problem.attachments.all().count(), 0)

    def test_assign_points_from_file(self):
        filename = get_test_filename('test_scores.zip')
        call_command('addproblem', filename)
        problem = Problem.objects.get()

        tests = Test.objects.filter(
            problem_instance=problem.main_problem_instance)

        self.assertEqual(tests.get(name='1a').max_score, 42)
        self.assertEqual(tests.get(name='1b').max_score, 42)
        self.assertEqual(tests.get(name='1c').max_score, 42)
        self.assertEqual(tests.get(name='2').max_score, 23)

    def test_assign_points_nonexistent(self):
        filename = get_test_filename('test_scores_nonexistent_fail.zip')
        self.assertRaises(CommandError, call_command, 'addproblem', filename)
        call_command('addproblem', filename, "nothrow")
        self.assertEqual(Problem.objects.count(), 0)
        package = ProblemPackage.objects.get()
        self.assertEqual(package.status, "ERR")
        # Check if error message is relevant to the issue
        self.assertIn("no such test group exists", package.info)

    def test_assign_points_not_exhaustive(self):
        filename = get_test_filename('test_scores_notexhaustive_fail.zip')
        self.assertRaises(CommandError, call_command, 'addproblem', filename)
        call_command('addproblem', filename, "nothrow")
        self.assertEqual(Problem.objects.count(), 0)
        package = ProblemPackage.objects.get()
        self.assertEqual(package.status, "ERR")
        # Check if error message is relevant to the issue
        self.assertIn("Score for group", package.info)
        self.assertIn("not found", package.info)

    @attr('slow')
    @both_configurations
    @override_settings(CONTEST_MODE=ContestMode.neutral)
    def test_huge_unpack_update(self):
        self.client.login(username='test_admin')
        filename = get_test_filename('test_huge_package.tgz')
        call_command('addproblem', filename)
        problem = Problem.objects.get()

        # Rudimentary test of package updating
        url = reverse('add_or_update_problem') + '?' + \
              urllib.urlencode({'problem': problem.id})
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        url = response.redirect_chain[-1][0]
        response = self.client.post(url,
            {'package_file': open(filename, 'rb')}, follow=True)
        self.assertEqual(response.status_code, 200)
        url = reverse('oioioiadmin:problems_problempackage_changelist')
        self.assertRedirects(response, url)

    def _check_no_ingen_package(self, problem, doc=True):
        self.assertEqual(problem.short_name, 'test')

        tests = Test.objects.filter(
                problem_instance=problem.main_problem_instance)
        t0 = tests.get(name='0')
        self.assertEqual(t0.input_file.read(), '0 0\n')
        self.assertEqual(t0.output_file.read(), '0\n')
        self.assertEqual(t0.kind, 'EXAMPLE')
        self.assertEqual(t0.group, '0')
        self.assertEqual(t0.max_score, 0)
        self.assertEqual(t0.time_limit, DEFAULT_TIME_LIMIT)
        self.assertEqual(t0.memory_limit, DEFAULT_MEMORY_LIMIT)
        t1a = tests.get(name='1a')
        self.assertEqual(t1a.input_file.read(), '0 0\n')
        self.assertEqual(t1a.output_file.read(), '0\n')
        self.assertEqual(t1a.kind, 'NORMAL')
        self.assertEqual(t1a.group, '1')
        self.assertEqual(t1a.max_score, 100)
        self.assertEqual(t1a.time_limit, DEFAULT_TIME_LIMIT)
        self.assertEqual(t1a.memory_limit, DEFAULT_MEMORY_LIMIT)
        t1b = tests.get(name='1b')
        self.assertEqual(t1b.input_file.read(), '0 0\n')
        self.assertEqual(t1b.output_file.read(), '0\n')
        self.assertEqual(t1b.kind, 'NORMAL')
        self.assertEqual(t1b.group, '1')
        self.assertEqual(t1b.max_score, 100)
        self.assertEqual(t1b.time_limit, DEFAULT_TIME_LIMIT)
        self.assertEqual(t1b.memory_limit, DEFAULT_MEMORY_LIMIT)

        model_solutions = ModelSolution.objects.filter(problem=problem)
        sol = model_solutions.get(name='test.c')
        self.assertEqual(sol.kind, 'NORMAL')
        self.assertEqual(model_solutions.count(), 1)

    @both_configurations
    def test_no_ingen_package(self):
        filename = get_test_filename('test_no_ingen_package.tgz')
        call_command('addproblem', filename)
        problem = Problem.objects.get()
        self._check_no_ingen_package(problem)

        # Rudimentary test of package updating
        call_command('updateproblem', str(problem.id), filename)
        problem = Problem.objects.get()
        self._check_no_ingen_package(problem)

    def _check_full_package(self, problem, doc=True):
        self.assertEqual(problem.short_name, 'sum')

        config = ExtraConfig.objects.get(problem=problem)
        assert 'extra_compilation_args' in config.parsed_config

        if doc:
            self.assertEqual(problem.name, u'Sumżyce')
            if settings.USE_SINOLPACK_MAKEFILES:
                statements = ProblemStatement.objects.filter(problem=problem)
                self.assertEqual(statements.count(), 1)
                self.assert_(statements.get().content.read()
                        .startswith('%PDF'))
        else:
            self.assertEqual(problem.name, u'sum')

        tests = Test.objects.filter(
                problem_instance=problem.main_problem_instance)
        t0 = tests.get(name='0')
        self.assertEqual(t0.input_file.read(), '1 2\n')
        self.assertEqual(t0.output_file.read(), '3\n')
        self.assertEqual(t0.kind, 'EXAMPLE')
        self.assertEqual(t0.group, '0')
        self.assertEqual(t0.max_score, 0)
        self.assertEqual(t0.time_limit, DEFAULT_TIME_LIMIT)
        self.assertEqual(t0.memory_limit, 133000)
        t1a = tests.get(name='1a')
        self.assertEqual(t1a.kind, 'NORMAL')
        self.assertEqual(t1a.group, '1')
        self.assertEqual(t1a.max_score, 33)
        t1b = tests.get(name='1b')
        self.assertEqual(t1b.kind, 'NORMAL')
        self.assertEqual(t1b.group, '1')
        self.assertEqual(t1b.max_score, 33)
        self.assertEqual(t1b.time_limit, 100)
        t1ocen = tests.get(name='1ocen')
        self.assertEqual(t1ocen.kind, 'EXAMPLE')
        self.assertEqual(t1ocen.group, '1ocen')
        self.assertEqual(t1ocen.max_score, 0)
        t2 = tests.get(name='2')
        self.assertEqual(t2.kind, 'NORMAL')
        self.assertEqual(t2.group, '2')
        self.assertEqual(t2.max_score, 33)
        t3 = tests.get(name='3')
        self.assertEqual(t3.kind, 'NORMAL')
        self.assertEqual(t3.group, '3')
        self.assertEqual(t3.max_score, 34)
        self.assertEqual(tests.count(), 6)

        checker = OutputChecker.objects.get(problem=problem)
        self.assertTrue(bool(checker.exe_file))

        extra_files = ExtraFile.objects.filter(problem=problem)
        self.assertEqual(extra_files.count(), 1)
        self.assertEqual(extra_files.get().name, 'makra.h')

        model_solutions = \
            ModelSolution.objects.filter(problem=problem).order_by('order_key')
        sol = model_solutions.get(name='sum.c')
        self.assertEqual(sol.kind, 'NORMAL')
        sol1 = model_solutions.get(name='sum1.pas')
        self.assertEqual(sol1.kind, 'NORMAL')
        sols1 = model_solutions.get(name='sums1.cpp')
        self.assertEqual(sols1.kind, 'SLOW')
        solb0 = model_solutions.get(name='sumb0.c')
        self.assertEqual(solb0.kind, 'INCORRECT')
        self.assertEqual(model_solutions.count(), 4)
        self.assertEqual(list(model_solutions), [sol, sol1, sols1, solb0])

        tests = Test.objects.filter(
                problem_instance=problem.main_problem_instance)

    @attr('slow')
    @both_configurations
    def test_full_unpack_update(self):
        filename = get_test_filename('test_full_package.tgz')
        call_command('addproblem', filename)
        problem = Problem.objects.get()
        self._check_full_package(problem)

        # Rudimentary test of package updating
        call_command('updateproblem', str(problem.id), filename)
        problem = Problem.objects.get()
        self._check_full_package(problem)

    def _check_interactive_package(self, problem):
        self.assertEqual(problem.short_name, 'arc')

        config = ExtraConfig.objects.get(problem=problem)
        assert len(config.parsed_config['extra_compilation_args']) == 2
        assert len(config.parsed_config['extra_compilation_files']) == 3

        self.assertEqual(problem.name, u'arc')

        tests = Test.objects.filter(
            problem_instance=problem.main_problem_instance)

        t0 = tests.get(name='0')
        self.assertEqual(t0.input_file.read(), '3\n12\n5\n8\n3\n15\n8\n0\n')
        self.assertEqual(t0.output_file.read(), '12\n15\n8\n')
        self.assertEqual(t0.kind, 'EXAMPLE')
        self.assertEqual(t0.group, '0')
        self.assertEqual(t0.max_score, 0)
        self.assertEqual(t0.time_limit, DEFAULT_TIME_LIMIT)
        self.assertEqual(t0.memory_limit, 66000)
        t1a = tests.get(name='1a')
        self.assertEqual(t1a.input_file.read(),
                '0\n-435634223 1 30 23 130 0 -324556462\n')
        self.assertEqual(t1a.output_file.read(),
                """126\n126\n82\n85\n80\n64\n84\n5\n128\n66\n4\n79\n64\n96
22\n107\n84\n112\n92\n63\n125\n82\n1\n""")
        self.assertEqual(t1a.kind, 'NORMAL')
        self.assertEqual(t1a.group, '1')
        self.assertEqual(t1a.max_score, 50)
        t2a = tests.get(name='2a')
        self.assertEqual(t2a.input_file.read(),
                '0\n-435634223 1 14045 547 60000 0 -324556462\n')
        self.assertEqual(t2a.kind, 'NORMAL')
        self.assertEqual(t2a.group, '2')
        self.assertEqual(t2a.max_score, 50)

        checker = OutputChecker.objects.get(problem=problem)
        self.assertIsNotNone(checker.exe_file)

        extra_files = ExtraFile.objects.filter(problem=problem)
        self.assertEqual(extra_files.count(), 3)

        model_solutions = \
            ModelSolution.objects.filter(problem=problem).order_by('order_key')
        solc = model_solutions.get(name='arc.c')
        self.assertEqual(solc.kind, 'NORMAL')
        solcpp = model_solutions.get(name='arc1.cpp')
        self.assertEqual(solcpp.kind, 'NORMAL')
        solpas = model_solutions.get(name='arc2.pas')
        self.assertEqual(solpas.kind, 'NORMAL')
        self.assertEqual(list(model_solutions), [solc, solcpp, solpas])

        submissions = Submission.objects.all()
        for s in submissions:
            self.assertEqual(s.status, 'INI_OK')
            self.assertEqual(s.score, IntegerScore(100))

    @attr('slow')
    @both_configurations
    def test_interactive_task(self):
        filename = get_test_filename('test_interactive_package.tgz')
        call_command('addproblem', filename)
        problem = Problem.objects.get()
        self._check_interactive_package(problem)


@enable_both_unpack_configurations
class TestSinolPackageInContest(TransactionTestCase, TestStreamingMixin):
    fixtures = ['test_users', 'test_contest']

    @both_configurations
    def test_upload_and_download_package(self):
        ProblemInstance.objects.all().delete()

        contest = Contest.objects.get()
        contest.default_submissions_limit = 123
        contest.save()

        filename = get_test_filename('test_simple_package.zip')
        self.client.login(username='test_admin')
        url = reverse('oioioiadmin:problems_problem_add')
        response = self.client.get(url, {'contest_id': contest.id},
                follow=True)
        url = response.redirect_chain[-1][0]
        self.assertEqual(response.status_code, 200)
        self.assertIn('problems/add-or-update.html',
                [getattr(t, 'name', None) for t in response.templates])
        response = self.client.post(url,
                {'package_file': open(filename, 'rb')}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Problem.objects.count(), 1)
        self.assertEqual(ProblemInstance.objects.count(), 2)
        self.assertEquals(ProblemInstance.objects.get(contest=contest)
                          .submissions_limit, 123)

        contest.default_submissions_limit = 124
        contest.save()

        ## Delete tests and check if re-uploading will fix it.
        problem = Problem.objects.get()
        problem_instance = ProblemInstance.objects \
            .filter(contest__isnull=False).get()
        num_tests = problem_instance.test_set.count()
        for test in problem_instance.test_set.all():
            test.delete()
        problem_instance.save()
        # problem instances are independent
        problem_instance = problem.main_problem_instance
        self.assertEqual(problem_instance.test_set.count(), num_tests)
        num_tests = problem_instance.test_set.count()
        for test in problem_instance.test_set.all():
            test.delete()
        problem_instance.save()

        url = reverse('add_or_update_problem',
                kwargs={'contest_id': contest.id}) + '?' + \
                        urllib.urlencode({
                                'problem': problem_instance.problem.id})
        response = self.client.get(url, follow=True)
        url = response.redirect_chain[-1][0]
        self.assertEqual(response.status_code, 200)
        self.assertIn('problems/add-or-update.html',
                [getattr(t, 'name', None) for t in response.templates])
        response = self.client.post(url,
                {'package_file': open(filename, 'rb')}, follow=True)
        self.assertEqual(response.status_code, 200)
        problem_instance = ProblemInstance.objects \
            .filter(contest__isnull=False).get()
        self.assertEqual(problem_instance.test_set.count(), num_tests)
        self.assertEqual(problem_instance.submissions_limit, 123)
        problem_instance = problem.main_problem_instance
        self.assertEqual(problem_instance.test_set.count(), num_tests)

        response = self.client.get(
                reverse('oioioiadmin:problems_problem_download',
                    args=(problem_instance.problem.id,)))
        self.assertStreamingEqual(response, open(filename, 'rb').read())

    @both_configurations
    def test_inwer_failure_package(self):
        ProblemInstance.objects.all().delete()

        contest = Contest.objects.get()
        filename = get_test_filename('test_inwer_failure.zip')
        self.client.login(username='test_admin')
        url = reverse('oioioiadmin:problems_problem_add')
        response = self.client.get(url, {'contest_id': contest.id},
                follow=True)
        url = response.redirect_chain[-1][0]
        self.assertEqual(response.status_code, 200)
        response = self.client.post(url,
                {'package_file': open(filename, 'rb')}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Problem.objects.count(), 0)
        self.assertEqual(ProblemInstance.objects.count(), 0)
        problem_package = ProblemPackage.objects.get()
        self.assertEqual(problem_package.status, 'ERR')
        if settings.USE_SINOLPACK_MAKEFILES:
            self.assertIn("Failed to execute command: make inwer",
                    problem_package.info)
        else:
            self.assertIn("Inwer failed", problem_package.info)


class TestSinolPackageCreator(TestCase, TestStreamingMixin):
    fixtures = ['test_users', 'test_full_package',
            'test_problem_instance_with_no_contest']

    def test_sinol_package_creator(self):
        problem = Problem.objects.get()
        self.client.login(username='test_admin')
        response = self.client.get(
                reverse('oioioiadmin:problems_problem_download',
                    args=(problem.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        stream = StringIO(self.streamingContent(response))
        zip = zipfile.ZipFile(stream, 'r')
        self.assertEqual(sorted(zip.namelist()), [
                'sum/doc/sumzad.pdf',
                'sum/in/sum0.in',
                'sum/in/sum1a.in',
                'sum/in/sum1b.in',
                'sum/in/sum1ocen.in',
                'sum/in/sum2.in',
                'sum/in/sum3.in',
                'sum/out/sum0.out',
                'sum/out/sum1a.out',
                'sum/out/sum1b.out',
                'sum/out/sum1ocen.out',
                'sum/out/sum2.out',
                'sum/out/sum3.out',
                'sum/prog/sum.c',
                'sum/prog/sum1.pas',
                'sum/prog/sumb0.c',
                'sum/prog/sums1.cpp',
            ])


class TestJudging(TestCase):
    fixtures = ['test_users', 'test_contest', 'test_full_package',
            'test_problem_instance']

    def test_judging(self):
        self.client.login(username='test_user')
        contest = Contest.objects.get()
        url = reverse('submit', kwargs={'contest_id': contest.id})

        # Show submission form
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('contests/submit.html',
                [getattr(t, 'name', None) for t in response.templates])
        form = response.context['form']
        self.assertEqual(len(form.fields['problem_instance_id'].choices), 1)
        pi_id = form.fields['problem_instance_id'].choices[0][0]

        # Submit
        filename = get_test_filename('sum-various-results.cpp')
        response = self.client.post(url, {
            'problem_instance_id': pi_id, 'file': open(filename, 'rb')})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Submission.objects.count(), 1)
        self.assertEqual(TestReport.objects.count(), 6)
        self.assertEqual(TestReport.objects.filter(status='OK').count(), 4)
        self.assertEqual(TestReport.objects.filter(status='WA').count(), 1)
        self.assertEqual(TestReport.objects.filter(status='RE').count(), 1)
        submission = Submission.objects.get()
        self.assertEqual(submission.status, 'INI_OK')
        self.assertEqual(submission.score, IntegerScore(34))

        urc = UserResultForContest.objects.get()
        self.assertEqual(urc.score, IntegerScore(34))


class TestLimits(TestCase):
    fixtures = ['test_users', 'test_contest']

    def upload_package(self):
        ProblemInstance.objects.all().delete()
        contest = Contest.objects.get()
        filename = get_test_filename('test_simple_package.zip')

        self.client.login(username='test_admin')
        url = reverse('oioioiadmin:problems_problem_add')
        response = self.client.get(url, {'contest_id': contest.id},
                follow=True)
        url = response.redirect_chain[-1][0]

        self.assertEqual(response.status_code, 200)
        self.assertIn('problems/add-or-update.html',
                [getattr(t, 'name', None) for t in response.templates])
        return self.client.post(url,
                {'package_file': open(filename, 'rb')}, follow=True)

    @override_settings(MAX_TEST_TIME_LIMIT_PER_PROBLEM=2000)
    def test_time_limit(self):
        response = self.upload_package()
        self.assertIn("Sum of time limits for all tests is too big. It&#39;s "
                      "50s, but it shouldn&#39;t exceed 2s.", response.content)

    @override_settings(MAX_MEMORY_LIMIT_FOR_TEST=10)
    def test_memory_limit(self):
        response = self.upload_package()
        self.assertIn("Memory limit mustn&#39;t be greater than %dKiB"
                        % settings.MAX_MEMORY_LIMIT_FOR_TEST, response.content)
