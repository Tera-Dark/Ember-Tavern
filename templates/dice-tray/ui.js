(() => {
  const root = document.getElementById('plugin-root');
  let expression = '2d6+1', busy = false, result = null;
  function render(ctx) {
    root.replaceChildren();
    const card = document.createElement('section');
    card.className = 'card';
    const title = document.createElement('h2');
    title.textContent = '桌面骰盘';
    const note = document.createElement('p');
    note.className = 'note';
    note.textContent = '自由掷骰不修改角色。结果由服务器生成并写入全房间事件；不是客户端随机动画。';
    const row = document.createElement('div');
    row.className = 'row';
    row.style.marginTop = '24px';
    const input = document.createElement('input');
    input.value = expression;
    input.maxLength = 16;
    input.setAttribute('aria-label', '骰盘表达式');
    input.oninput = () => { expression = input.value; };
    const button = document.createElement('button');
    button.className = 'primary';
    button.textContent = busy ? '服务器掷骰中…' : '服务器掷骰';
    button.disabled = busy || !ctx.resources['core.dice/v1'];
    button.onclick = async () => {
      busy = true;
      render(EmberSDK.getContext());
      try { result = await EmberSDK.roll(expression); }
      catch (error) { EmberSDK.notify(error.message, 'error'); }
      finally { busy = false; render(EmberSDK.getContext()); }
    };
    row.append(input, button);
    const outcome = document.createElement('p');
    outcome.style.cssText = 'font-size:24px;margin-top:24px;overflow-wrap:anywhere';
    outcome.textContent = result ? `${result.expression} → [${result.rolls.join(', ')}] ${result.modifier >= 0 ? '+' : ''}${result.modifier} = ${result.total}` : '等待命运留下一个数字。';
    const rule = document.createElement('p');
    rule.className = 'note';
    rule.textContent = ctx.resources['core.rules/v1']?.data.description || '尚未取得规则契约';
    card.append(title, note, row, outcome, rule);
    root.append(card);
  }
  EmberSDK.onContext(render);
})();
