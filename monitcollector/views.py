from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import  render, redirect
from django.template.loader import render_to_string
from django.core.urlresolvers import reverse
from django.contrib.admin.views.decorators import staff_member_required

from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
import subprocess
import socket

from monitcollector.models import collect_data, Server, Process, System
import settings

try:
    monit_update_period = settings.MONIT_UPDATE_PERIOD
except:
    monit_update_period = 60

@csrf_exempt
def collector(request):
    # only allow POSTs
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    data = request.body
    
    # for testing
    # with open("xml.xml", "w") as f:
    #     f.write(data)
    
    collected = collect_data(data)
    if not collected:
        return HttpResponse('wrong data format')
    return HttpResponse('ok')
   
@staff_member_required
def dashboard(request):
    if Server.objects.all().count() > 0:
        servers = Server.objects.all().order_by('localhostname')
        return render(request, 'monitcollector/dashboard.html',{'servers': servers, 'server_found': True})
    else:
       return render(request, 'monitcollector/dashboard.html',{'server_found': False})

@staff_member_required
def server(request, server_id):
    # time = datetime.strptime(x, "%Y-%m-%d %H:%M:%S")
    # timedelta = (datetime.now()-load.date).total_seconds()*1000.
    try:
        server = Server.objects.get(id=server_id)
        system = server.system
        processes = server.process_set.all().order_by('name')
        return render(request, 'monitcollector/server.html',{'server': server, 'system':system, 'processes':processes, 'monit_update_period': monit_update_period})
    except ObjectDoesNotExist:
        return render(request, 'monitcollector/dashboard.html',{'server_found': False})

@staff_member_required
def process(request, server_id, process_name):
  try:
    server = Server.objects.get(id=server_id)
    process = server.process_set.get(name=process_name)
    this_server = check_this_server(server)
    return render(request, 'monitcollector/process.html',{'process_found': True, 'server': server, 'process': process, 'monit_update_period': monit_update_period, 'this_server': this_server})
  except ObjectDoesNotExist:
    return render(request, 'monitcollector/process.html',{'process_found': False})

@staff_member_required
def process_action(request, server_id):
    if not request.POST:
        return HttpResponseNotAllowed(['POST'])
    action = request.POST['action']
    process_name = request.POST['process']
    server = Server.objects.get(id=server_id)
    if check_this_server(server):
        process = server.process_set.get(name=process_name)
        action_labels = {'start': 'starting...', 'stop': 'stopping...', 'restart': 'restarting...', 'unmonitor': 'disable monitoring...', 'monitor': 'enable monitoring...'}
        if action in action_labels:
            process.status = action_labels.get(action)
            if action == 'unmonitor':
                process.monitor = 0
            elif action == 'monitor':
                process.monitor = 2
            process.save()
        subprocess.call(["monit", action, process_name])
    return redirect(reverse('monitcollector.views.process', kwargs={'server_id': server.id, 'process_name': process_name}))  # '/monitcollector/server/%s/process/%s' % (server.id, process_name)

@staff_member_required
def confirm_delete(request, server_id):
    server = Server.objects.get(id=server_id)
    return render(request, "monitcollector/confirm_delete.html", {"server": server})

@staff_member_required
def delete_server(request, server_id):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    server = Server.objects.get(id=server_id)
    server.delete()
    return redirect(reverse('monitcollector.views.dashboard'))

### ajax loading views ###
def load_dashboard_table(request):
    servers = Server.objects.all().order_by('localhostname')
    table_html = render_to_string('monitcollector/includes/dashboard_table.html',{'servers': servers})
    return JsonResponse({'table_html': table_html})

def load_system_table(request, server_id):
    server = Server.objects.get(id=server_id)
    processes = server.process_set.all().order_by('name')
    table_html = render_to_string('monitcollector/includes/server_table.html',{'server': server, 'processes': processes})
    return JsonResponse({'table_html': table_html})

def load_process_table(request, server_id, process_name):
    server = Server.objects.get(id=server_id)
    process = server.process_set.get(name=process_name)
    table_html = render_to_string('monitcollector/includes/process_table.html',{'process': process})
    return JsonResponse({'table_html': table_html})

def load_system_data(request, server_id):
    server = Server.objects.get(id=server_id)
    system = server.system
    processes = server.process_set.all().order_by('name')
    table_html = render_to_string('monitcollector/includes/server_table.html',{'server': server, 'processes': processes})
    data = {'table_html': table_html, 'date': system.date_last, 'load_avg01': system.load_avg01_last,
            'load_avg05': system.load_avg05_last, 'load_avg15': system.load_avg15_last, 'cpu_user': system.cpu_user_last,
            'cpu_system': system.cpu_system_last, 'cpu_wait': system.cpu_wait_last, 'memory_percent': system.memory_percent_last,
            'memory_kilobyte': system.memory_kilobyte_last, 'swap_percent': system.swap_percent_last, 'swap_kilobyte': system.swap_kilobyte_last}
    return JsonResponse(data)

def load_process_data(request, server_id, process_name):
    server = Server.objects.get(id=server_id)
    process = server.process_set.get(name=process_name)
    table_html = render_to_string('monitcollector/includes/process_table.html',{'process': process})
    data = {'date': process.date_last, 'cpu_percenttotal': process.cpu_percenttotal_last,
            'memory_percenttotal': process.memory_percenttotal_last, 'memory_kilobytetotal': process.memory_kilobytetotal_last}
    return JsonResponse(data)

# checks if this is the server where monitcollector is installed
def check_this_server(server):
    if server.localhostname == socket.gethostname():
        return True
    return False

