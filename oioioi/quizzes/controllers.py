import logging

from django.core.exceptions import ValidationError
from oioioi.problems.controllers import ProblemController
from oioioi.quizzes.models import *

from django.utils.translation import ugettext_lazy as _
from django import forms
from django.db import transaction
from django.template import RequestContext
from oioioi.contests.controllers import ContestController, \
        submission_template_context
from django.template.loader import render_to_string


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

    def _field_name_for_question(self, problem_instance, question):
        return 'quiz_' + str(problem_instance.id) + '_q_' + str(question.id)

    def validate_submission_form(self, request, problem_instance, form,
            cleaned_data):

        questions = problem_instance.problem.quiz.quizquestion_set.all()
        for question in questions:
            field_name = self._field_name_for_question(problem_instance,
                                                       question)
            if field_name in form.errors.as_data():
                continue  # already has a validation error

            data = cleaned_data[field_name]
            if question.is_multiple_choice:
                answers = [int(a) for a in data]
            else:
                if data == '':
                    form.add_error(field_name, _("Answer is required here."))
                    answers = []
                else:
                    answers = [int(data)]

            # TODO not sure if this is needed - the Field itself should check it
            for aid in answers:
                answer = QuizAnswer.objects.get(id=aid)
                if answer.question != question:
                    # This answer is to some other question.
                    # Something bad is going on.
                    raise ValidationError(_("Illegal answer"))

        return cleaned_data

    def adjust_submission_form(self, request, form, problem_instance):
        questions = problem_instance.problem.quiz.quizquestion_set.all()

        for question in questions:
            answers = question.quizanswer_set.values_list('id', 'answer')
            field_name = self._field_name_for_question(problem_instance,
                                                       question)
            if question.is_multiple_choice:
                form.fields[field_name] = forms.MultipleChoiceField(
                    label=question.question,
                    choices=answers,
                    widget=forms.CheckboxSelectMultiple,
                    required=False
                )
            else:
                form.fields[field_name] = forms.ChoiceField(
                    label=question.question,
                    choices=answers,
                    widget=forms.RadioSelect,
                    required=False
                )
            form.set_custom_field_attributes(field_name, problem_instance)

    def create_submission(self, request, problem_instance, form_data,
                          judge_after_create=True,
                          **kwargs):

        with transaction.atomic():
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
            logger.warn("SUBMITTING")

            # add answers to submission
            questions = problem_instance.problem.quiz.quizquestion_set.all()
            for question in questions:
                field_name = self._field_name_for_question(problem_instance,
                                                           question)
                if question.is_multiple_choice:
                    answers = [int(a) for a in form_data.get(field_name)]
                else:
                    answers = [int(form_data.get(field_name))]

                for a in answers:
                    answer = QuizAnswer.objects.get(id=a)
                    sub = QuizSubmissionAnswer.objects.create(
                        quiz_submission=submission,
                        answer=answer
                    )
                    sub.save()

        if judge_after_create:
            problem_instance.controller.judge(submission)
        return submission

    def render_submission(self, request, submission):
        problem_instance = submission.problem_instance

        # TODO this is just for testing but may be repurposed for actual view
        questions = problem_instance.problem.quiz.quizquestion_set.all()
        qa = {}
        # prepare base question-answer structure
        for q in questions:
            qa[q.id] = {
                'question': q.question,
                'answers': {}
            }
            for a in q.quizanswer_set.all():
                qa[q.id]['answers'][a.id] = {
                    'text': a.answer,
                    'selected': False
                }

        # fill-in which answers have been selected
        for qsa in submission.quizsubmission.quizsubmissionanswer_set.all():
            qid = qsa.answer.question.id
            aid = qsa.answer.id
            qa[qid]['answers'][aid]['selected'] = True

        # get rid of keys
        for k in qa:
            qa[k]['answers'] = qa[k]['answers'].values()
        qa = qa.values()

        return render_to_string('quizzes/submission_header.html',
                context_instance=RequestContext(request,
                    {'submission': submission_template_context(request,
                        submission.quizsubmission),
                    'saved_diff_id': request.session.get('saved_diff_id'),
                    'questions_answers': qa,  # TODO
                    'supported_extra_args':
                        problem_instance.controller.get_supported_extra_args(
                            submission),
                    'can_admin': False}))  # TODO