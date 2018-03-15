from django.db import models
from django.utils.translation import ugettext_lazy as _

from oioioi.contests.models import Submission
from oioioi.problems.models import Problem


class Quiz(Problem):
    pass


class QuizQuestion(models.Model):
    question = models.CharField(max_length=140, verbose_name=_("question"))
    is_multiple_choice = models.BooleanField(default=False, verbose_name=_(
        "is multiple choice"))
    quiz = models.ForeignKey(Quiz, verbose_name=_("quiz"))


class QuizAnswer(models.Model):
    question = models.ForeignKey(QuizQuestion, verbose_name=_("question"))
    answer = models.CharField(max_length=140, verbose_name=_("answer"))
    is_correct = models.BooleanField(default=False,
                                     verbose_name=_("is answer correct"))


class QuizSubmission(Submission):
    pass


class QuizSubmissionAnswer(models.Model):
    quiz_submission = models.ForeignKey(QuizSubmission,
                                        verbose_name=_("quiz submission"))
    answer = models.ForeignKey(QuizAnswer, verbose_name=_("answer"))
