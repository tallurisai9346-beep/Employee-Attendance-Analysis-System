function setAllStatuses(status) {
  document.querySelectorAll('.status-select').forEach(el => { el.value = status; });
}
document.querySelectorAll('.flash button').forEach(btn => btn.addEventListener('click', () => btn.parentElement.remove()));
