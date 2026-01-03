import asyncio
import json
import gradio as gr
from mcp import ClientSession
from mcp.client.sse import sse_client
from contextlib import AsyncExitStack

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

class SimpleMCPClient:
    def __init__(self):
        self.session = None
        self.connected = False
        self.tools = []
        self.exit_stack = None
        self.server_url = "https://chris4k-weather.hf.space/gradio_api/mcp/sse"
    
    def connect(self) -> str:
        """Connect to the hardcoded MCP server"""
        return loop.run_until_complete(self._connect())
    
    async def _connect(self) -> str:
        try:
            # Clean up previous connection
            if self.exit_stack:
                await self.exit_stack.aclose()
            
            self.exit_stack = AsyncExitStack()
            
            # Connect to SSE MCP server
            sse_transport = await self.exit_stack.enter_async_context(
                sse_client(self.server_url)
            )
            read_stream, write_callable = sse_transport
            
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(read_stream, write_callable)
            )
            await self.session.initialize()
            
            # Get available tools
            response = await self.session.list_tools()
            self.tools = response.tools
            
            self.connected = True
            tool_names = [tool.name for tool in self.tools]
            return f"✅ Connected to weather server!\nAvailable tools: {', '.join(tool_names)}"
            
        except Exception as e:
            self.connected = False
            return f"❌ Connection failed: {str(e)}"
    
    def get_weather(self, location: str) -> str:
        """Get weather for a location (city, country format)"""
        if not self.connected:
            return "❌ Not connected to server. Click Connect first."
        
        if not location.strip():
            return "❌ Please enter a location (e.g., 'Berlin, Germany')"
        
        return loop.run_until_complete(self._get_weather(location))
    
    async def _get_weather(self, location: str) -> str:
        try:
            # Parse location
            if ',' in location:
                city, country = [part.strip() for part in location.split(',', 1)]
            else:
                city = location.strip()
                country = ""
            
            # Find the weather tool
            weather_tool = next((tool for tool in self.tools if 'weather' in tool.name.lower()), None)
            if not weather_tool:
                return "❌ Weather tool not found on server"
            
            # Call the tool
            params = {"city": city, "country": country}
            result = await self.session.call_tool(weather_tool.name, params)
            
            # Extract content properly
            content_text = ""
            if hasattr(result, 'content') and result.content:
                if isinstance(result.content, list):
                    for content_item in result.content:
                        if hasattr(content_item, 'text'):
                            content_text += content_item.text
                        elif hasattr(content_item, 'content'):
                            content_text += str(content_item.content)
                        else:
                            content_text += str(content_item)
                elif hasattr(result.content, 'text'):
                    content_text = result.content.text
                else:
                    content_text = str(result.content)
            
            if not content_text:
                return "❌ No content received from server"
            
            try:
                # Try to parse as JSON
                parsed = json.loads(content_text)
                if isinstance(parsed, dict):
                    if 'error' in parsed:
                        return f"❌ Error: {parsed['error']}"
                    
                    # Format weather data nicely
                    if 'current_weather' in parsed:
                        weather = parsed['current_weather']
                        formatted = f"🌍 **{parsed.get('location', 'Unknown')}**\n\n"
                        formatted += f"🌡️ Temperature: {weather.get('temperature_celsius', 'N/A')}°C\n"
                        formatted += f"🌤️ Conditions: {weather.get('weather_description', 'N/A')}\n"
                        formatted += f"💨 Wind: {weather.get('wind_speed_kmh', 'N/A')} km/h\n"
                        formatted += f"💧 Humidity: {weather.get('humidity_percent', 'N/A')}%\n"
                        return formatted
                    elif 'temperature (°C)' in parsed:
                        # Handle the original format from your server
                        formatted = f"🌍 **{parsed.get('location', 'Unknown')}**\n\n"
                        formatted += f"🌡️ Temperature: {parsed.get('temperature (°C)', 'N/A')}°C\n"
                        formatted += f"🌤️ Weather Code: {parsed.get('weather_code', 'N/A')}\n"
                        formatted += f"🕐 Timezone: {parsed.get('timezone', 'N/A')}\n"
                        formatted += f"🕒 Local Time: {parsed.get('local_time', 'N/A')}\n"
                        return formatted
                    else:
                        return f"✅ Weather data:\n```json\n{json.dumps(parsed, indent=2)}\n```"
                        
            except json.JSONDecodeError:
                # If not JSON, return as text
                return f"✅ Weather data:\n```\n{content_text}\n```"
            
            return f"✅ Raw result:\n{content_text}"
            
        except Exception as e:
            return f"❌ Failed to get weather: {str(e)}"

# Global client
client = SimpleMCPClient()

def create_interface():
    with gr.Blocks(title="Weather MCP Test", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🌤️ Weather MCP Test Client")
        gr.Markdown("Simple client to test the weather MCP server")
        
        # Connection
        with gr.Row():
            connect_btn = gr.Button("🔌 Connect to Weather Server", variant="primary")
            status = gr.Textbox(
                label="Status", 
                value="Click Connect to start",
                interactive=False,
                scale=2
            )
        
        # Weather query
        with gr.Group():
            gr.Markdown("### Get Weather")
            with gr.Row():
                location_input = gr.Textbox(
                    label="Location", 
                    placeholder="e.g., Berlin, Germany",
                    value="Berlin, Germany",
                    scale=3
                )
                weather_btn = gr.Button("🌡️ Get Weather", scale=1)
            
            weather_result = gr.Textbox(
                label="Weather Result",
                interactive=False,
                lines=8,
                placeholder="Weather information will appear here..."
            )
        
        # Examples
        with gr.Group():
            gr.Markdown("### 📝 Examples")
            examples = gr.Examples(
                examples=[
                    ["Berlin, Germany"],
                    ["Tokyo, Japan"], 
                    ["New York, USA"],
                    ["London, UK"],
                    ["Sydney, Australia"]
                ],
                inputs=[location_input]
            )
        
        # Event handlers
        connect_btn.click(
            client.connect,
            outputs=[status]
        )
        
        weather_btn.click(
            client.get_weather,
            inputs=[location_input],
            outputs=[weather_result]
        )
        
        location_input.submit(
            client.get_weather,
            inputs=[location_input],
            outputs=[weather_result]
        )
    
    return demo

if __name__ == "__main__":
    interface = create_interface()
    interface.launch(debug=True, share=True, mcp_server=True)