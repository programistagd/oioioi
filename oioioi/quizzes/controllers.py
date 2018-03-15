import logging

from oioioi.problems.controllers import ProblemController
from oioioi.quizzes.models import *

from django.utils.translation import ugettext_lazy as _
from django import forms


logger = logging.getLogger(__name__)


class QuizProblemController(ProblemController):
    """Defines rules for quizzes.

    """

    modules_with_subclasses = ['controllers']
    abstract = True

    def __init__(self, *args, **kwargs):
        super(QuizProblemController, self).__init__(*args, **kwargs)

    def adjust_problem(self):
        """Called whan a (usually new) problem has just got the controller
           attached or after the problem has been modified.
        """
        pass

    def judge(self, submission, extra_args=None, is_rejudge=False):
        pass  # TODO scoring?

    def mixins_for_admin(self):
        """Returns an iterable of mixins to add to the default
           :class:`oioioi.problems.admin.ProblemAdmin` for
           this particular problem.

           The default implementation returns an empty tuple.
        """
        return ()  # TODO editing???

    def update_user_result_for_problem(self, result):
        pass  # TODO scoring?

    def update_user_results(self, user, problem_instance):
        pass  # TODO scoring?

    def validate_submission_form(self, request, problem_instance, form,
            cleaned_data):
        return cleaned_data

    def adjust_submission_form(self, request, form, problem_instance):
        pid = str(problem_instance.id)
        pname = problem_instance.short_name + ": " + problem_instance.problem.name
        form.fields['test_' + pid] = forms.CharField(
            label=_("Problem: %s") % pname)
        form.set_custom_field_attributes('test_' + pid, problem_instance)

    def create_submission(self, request, problem_instance, form_data,
                          judge_after_create=True,
                          **kwargs):
        submission = QuizSubmission(
            user=form_data.get('user', request.user),
            problem_instance=problem_instance,
            kind=form_data.get('kind',
                               problem_instance.controller.get_default_submission_kind(
                                   request,
                                   problem_instance=problem_instance)),
            date=request.timestamp
        )

        submission.save()

        # TODO create submission answers
        # also maybe transaction to not have partially added submission if sth goes wrong?

        if judge_after_create:
            problem_instance.controller.judge(submission)
        return submission
