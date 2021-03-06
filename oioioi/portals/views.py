import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404, HttpResponse
from django.utils.translation import ugettext_lazy as _
from django.utils.safestring import mark_safe
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.template.loader import render_to_string
from django.contrib.auth.models import User
from django.db import IntegrityError
from mptt.exceptions import InvalidMove
from oioioi.base.permissions import enforce_condition, is_superuser, \
        not_anonymous
from oioioi.base.menu import account_menu_registry
from oioioi.base.main_page import register_main_page_view
from oioioi.portals.models import Node, Portal
from oioioi.portals.forms import NodeForm
from oioioi.portals.actions import node_actions, portal_actions, \
        register_node_action, register_portal_action, portal_url, \
        DEFAULT_ACTION_NAME
from oioioi.portals.widgets import render_panel
from oioioi.portals.utils import resolve_path
from oioioi.portals.conditions import is_portal_admin, current_node_is_root, \
        global_portal_exists

# pylint: disable=W0611
import oioioi.portals.handlers


@register_main_page_view(order=500, condition=global_portal_exists)
def main_page_view(request):
    return redirect('global_portal', portal_path='')


@enforce_condition(is_superuser, login_redirect=False)
def create_global_portal_view(request):
    portal_queryset = Portal.objects.filter(owner=None)
    if portal_queryset.exists():
        return redirect(portal_url(portal=portal_queryset.get()))

    if request.method != 'POST':
        return render(request, 'portals/create-global-portal.html')
    else:
        if 'confirmation' in request.POST:
            name = render_to_string(
                    'portals/global-portal-initial-main-page-name.txt')
            body = render_to_string(
                    'portals/global-portal-initial-main-page-body.txt')
            root = Node.objects.create(full_name=name, short_name='',
                                       parent=None, panel_code=body)
            portal = Portal.objects.create(owner=None, root=root)
            return redirect(portal_url(portal=portal))
        else:
            return redirect('/')


@enforce_condition(not_anonymous, login_redirect=False)
def create_user_portal_view(request):
    portal_queryset = Portal.objects.filter(owner=request.user)
    if portal_queryset.exists():
        return redirect(portal_url(portal=portal_queryset.get()))

    if request.method != 'POST':
        return render(request, 'portals/create-user-portal.html')
    else:
        if 'confirmation' in request.POST:
            name = render_to_string(
                    'portals/user-portal-initial-main-page-name.txt')
            body = render_to_string(
                    'portals/user-portal-initial-main-page-body.txt')
            root = Node.objects.create(full_name=name, short_name='',
                                       parent=None, panel_code=body)
            portal = Portal.objects.create(owner=request.user, root=root)
            return redirect(portal_url(portal=portal))
        else:
            return redirect('/')


def _portal_view(request, portal, portal_path):
    if 'action' in request.GET:
        action = request.GET['action']
    else:
        action = DEFAULT_ACTION_NAME

    request.portal = portal
    request.action = action

    if action in node_actions:
        request.current_node = resolve_path(request.portal, portal_path)
        view = node_actions[action]
    elif action in portal_actions:
        view = portal_actions[action]
    else:
        raise Http404

    return view(request)


def global_portal_view(request, portal_path):
    portal = get_object_or_404(Portal, owner=None)
    return _portal_view(request, portal, portal_path)


def user_portal_view(request, username, portal_path):
    portal = get_object_or_404(Portal, owner__username=username)
    return _portal_view(request, portal, portal_path)


@register_node_action('show_node', menu_text=_("Show node"), menu_order=100)
def show_node_view(request):
    rendered_panel = mark_safe(render_panel(request,
                                            request.current_node.panel_code))
    return render(request, 'portals/show-node.html',
                  {'rendered_panel': rendered_panel})


@register_node_action('edit_node', condition=is_portal_admin,
                      menu_text=_("Edit node"), menu_order=200)
def edit_node_view(request):
    if request.method != 'POST':
        form = NodeForm(instance=request.current_node)
    else:
        form = NodeForm(request.POST, instance=request.current_node)
        if form.is_valid():
            node = form.save()
            return redirect(portal_url(node=node))

    return render(request, 'portals/edit-node.html', {'form': form})


@register_node_action('add_node', condition=is_portal_admin,
                      menu_text=_("Add child node"), menu_order=300)
def add_node_view(request):
    if request.method != 'POST':
        form = NodeForm(initial={'parent': request.current_node})
    else:
        instance = Node(parent=request.current_node)
        form = NodeForm(request.POST, instance=instance)
        if form.is_valid():
            node = form.save()
            return redirect(portal_url(node=node))

    return render(request, 'portals/add-node.html', {'form': form})


@register_node_action('delete_node',
                      condition=is_portal_admin & ~current_node_is_root,
                      menu_text=_("Delete node"), menu_order=400)
def delete_node_view(request):
    if request.method != 'POST':
        return render(request, 'portals/delete-node.html')
    else:
        if 'confirmation' in request.POST:
            parent = request.current_node.parent
            request.current_node.delete()
            return redirect(portal_url(node=parent))
        else:
            return redirect(portal_url(node=request.current_node))


@register_portal_action('manage_portal', condition=is_portal_admin,
                        menu_text=_("Manage portal"), menu_order=500)
def manage_portal_view(request):
    return render(request, 'portals/manage-portal.html')


@register_portal_action('portal_tree_json', condition=is_portal_admin)
def portal_tree_json_view(request):
    nodes = request.portal.root.get_descendants(include_self=True)
    json = render_to_string('portals/portal-tree.json', {'nodes': nodes})
    json = json.replace('}{', '},{')
    return HttpResponse(json)


def move_node_view(request):
    position_mapping = {'before': 'left', 'after': 'right',
                        'inside': 'first-child'}
    position = request.GET['position']
    if position not in position_mapping:
        raise SuspiciousOperation
    position = position_mapping[position]

    try:
        target = Node.objects.get(pk=request.GET['target'])
    except Node.DoesNotExist:
        raise SuspiciousOperation
    target_portal = target.get_root().portal

    request.portal = target_portal
    if not is_portal_admin(request):
        raise SuspiciousOperation
    if position != 'first-child' and target.is_root_node():
        raise SuspiciousOperation

    try:
        node = Node.objects.get(pk=request.GET['node'])
    except Node.DoesNotExist:
        raise SuspiciousOperation
    if node.get_root().portal != target_portal:
        raise SuspiciousOperation

    try:
        node.move_to(target, position)
    except (InvalidMove, IntegrityError):
        raise SuspiciousOperation

    return HttpResponse()


@register_portal_action('delete_portal', condition=is_portal_admin)
def delete_portal_view(request):
    if request.method != 'POST':
        return render(request, 'portals/delete-portal.html')
    else:
        if 'confirmation' in request.POST:
            request.portal.root.delete()
            request.portal.delete()
            return redirect('/')
        else:
            return redirect(portal_url(portal=request.portal,
                                       action='manage_portal'))


def my_portal_url(request):
    try:
        return portal_url(portal=request.user.portal)
    except Portal.DoesNotExist:
        return reverse('create_user_portal')


@enforce_condition(not_anonymous, login_redirect=False)
def render_markdown_view(request):
    if request.method != 'POST' or 'markdown' not in request.POST:
        raise Http404
    rendered = render_panel(request, request.POST['markdown'])
    return HttpResponse(json.dumps({'rendered': rendered}),
                        content_type='application/json')


account_menu_registry.register('my_portal', _("My portal"), my_portal_url,
        order=150)
