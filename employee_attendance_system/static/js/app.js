document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  document.querySelector('[data-sidebar-toggle]')?.addEventListener('click', () => sidebar?.classList.toggle('open'));

  const chartLayout = {
    font: { family: 'DM Sans, sans-serif', color: '#66665d', size: 10 },
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    margin: { t: 12, r: 12, b: 35, l: 35 },
    legend: { orientation: 'h', y: -0.22 },
    xaxis: { gridcolor: '#efede6', zeroline: false },
    yaxis: { gridcolor: '#efede6', zeroline: false },
  };
  const drawBars = (element, labels, series) => {
    if (!element || !window.Plotly) return;
    Plotly.newPlot(element, series.map(item => ({
      x: labels, y: item.values, name: item.name, type: 'bar',
      marker: { color: item.color, borderRadius: 3 },
    })), { ...chartLayout, barmode: 'group' }, { responsive: true, displayModeBar: false });
  };

  const adminTrend = document.getElementById('adminTrend');
  if (adminTrend) {
    const data = JSON.parse(adminTrend.dataset.chart || '[]');
    drawBars(adminTrend, data.map(item => item.label), [
      { name: 'Present', values: data.map(item => item.present), color: '#487a57' },
      { name: 'Absent', values: data.map(item => item.absent), color: '#bd6658' },
    ]);
  }
  const departmentChart = document.getElementById('departmentChart');
  if (departmentChart) {
    const data = JSON.parse(departmentChart.dataset.chart || '[]');
    if (data.length) Plotly.newPlot(departmentChart, [{
      labels: data.map(item => item[0]), values: data.map(item => item[1]), type: 'pie', hole: 0.62,
      marker: { colors: ['#d4ad3a', '#487a57', '#bd6658', '#7b8fa0', '#9c8752'] }, textinfo: 'label+percent',
    }], { ...chartLayout, showlegend: true, margin: { t: 8, r: 8, b: 8, l: 8 } }, { responsive: true, displayModeBar: false });
    else departmentChart.innerHTML = '<div class="empty-inline">No department data.</div>';
  }
  const employeeTrend = document.getElementById('employeeTrend');
  if (employeeTrend) {
    const data = JSON.parse(employeeTrend.dataset.chart || '{}');
    drawBars(employeeTrend, data.labels || [], [
      { name: 'Present', values: data.present || [], color: '#487a57' },
      { name: 'Absent', values: data.absent || [], color: '#bd6658' },
    ]);
  }
  const reportTrend = document.getElementById('reportTrend');
  if (reportTrend) {
    const data = JSON.parse(reportTrend.dataset.chart || '{}');
    const labels = data.map(item => item.label);
    const statuses = ['Present', 'Absent', 'Leave', 'Holiday'];
    const colors = { Present: '#487a57', Absent: '#bd6658', Leave: '#d4ad3a', Holiday: '#78899a' };
    drawBars(reportTrend, labels, statuses.map(status => ({
      name: status, color: colors[status], values: data.map(item => item[status] || 0),
    })));
  }
});