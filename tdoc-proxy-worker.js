// 腾讯文档 API 代理 - Cloudflare Worker
// 部署到 Cloudflare Workers 后，PA 免费版可通过此代理访问腾讯文档
// 
// 部署步骤：
// 1. 注册 https://dash.cloudflare.com （免费）
// 2. 进入 Workers & Pages → Create Worker
// 3. 把这段代码粘贴进去，点 Deploy
// 4. 记下分配的 xxx.workers.dev 地址
// 5. 把地址填到 flask_app_v3.py 的 TDOC_PROXY 变量中

export default {
  async fetch(request) {
    // 只允许 POST
    if (request.method !== 'POST') {
      return new Response(JSON.stringify({error: 'Method not allowed'}), {
        status: 405,
        headers: {'Content-Type': 'application/json'}
      });
    }

    try {
      const body = await request.json();
      
      // 验证必需字段
      if (!body.tool_name || !body.args) {
        return new Response(JSON.stringify({error: 'Missing tool_name or args'}), {
          status: 400,
          headers: {'Content-Type': 'application/json'}
        });
      }

      // 构造腾讯文档 MCP API 请求
      const payload = {
        jsonrpc: "2.0",
        method: "tools/call",
        params: {
          name: body.tool_name,
          arguments: body.args
        },
        id: 1
      };

      // 从请求头获取 Authorization（由 PA 后端传入）
      const auth = request.headers.get('X-TDoc-Token') || '';
      
      const resp = await fetch('https://docs.qq.com/openapi/mcp', {
        method: 'POST',
        headers: {
          'Authorization': auth,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      const data = await resp.json();
      
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*'
        }
      });
    } catch (e) {
      return new Response(JSON.stringify({error: e.message}), {
        status: 500,
        headers: {'Content-Type': 'application/json'}
      });
    }
  }
};
