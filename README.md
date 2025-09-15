# TMC - micro:bit Block Recognition App

A Flask web application that uses computer vision and AI to recognize micro:bit block programming images and provide intelligent code suggestions for students.

## Features

- **Image Recognition**: Upload photos of micro:bit block programs and get JavaScript code
- **AI-Powered Suggestions**: Get personalized feedback and creative ideas for extending your code
- **Smart Caching**: Intelligent caching system for improved performance
- **Modern UI**: Clean, responsive web interface designed for students
- **Real-time Processing**: Fast image processing with Google Cloud Vision API

## Technology Stack

- **Backend**: Flask (Python)
- **Computer Vision**: Google Cloud Vision API
- **AI Suggestions**: LM Studio (local LLM)
- **Frontend**: HTML, CSS, JavaScript
- **Block Mapping**: Comprehensive micro:bit block recognition system

## Quick Start

### Prerequisites

- Python 3.11+
- Google Cloud Vision API credentials
- LM Studio running locally (optional, for AI suggestions)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/riverpease15/tmc.git
   cd tmc
   ```

2. **Set up virtual environment**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   export FLASK_SECRET_KEY="your-secret-key"
   export GOOGLE_APPLICATION_CREDENTIALS="path/to/your/service-account.json"
   ```

5. **Run the application**
   ```bash
   python app.py
   ```
   
   Or use the provided script:
   ```bash
   ./run.sh
   ```

6. **Open your browser**
   Navigate to `http://localhost:5000`

## Usage

1. **Upload an Image**: Take a photo of your micro:bit block program or upload an existing image
2. **Get Code**: The app will analyze the image and generate JavaScript code
3. **Get Suggestions**: Click to receive AI-powered feedback and creative ideas
4. **Learn & Iterate**: Use the suggestions to extend and improve your programs

## Project Structure

```
tmc/
├── app.py                 # Main Flask application
├── vision_processor.py    # Image processing and OCR
├── requirements.txt       # Python dependencies
├── run.sh                # Setup and run script
├── static/
│   ├── blocks_map.json   # Block recognition mapping
│   ├── script.js         # Frontend JavaScript
│   ├── styles.css        # Styling
│   └── code_file.js      # Generated code output
├── templates/
│   └── code_box.html     # Main web interface
└── uploads/              # Temporary image storage
```

## API Endpoints

- `GET /` - Main application interface
- `POST /process_image_path` - Upload and process images
- `GET /get_js_content` - Retrieve generated JavaScript code
- `POST /generate_suggestions` - Get AI-powered suggestions
- `POST /generate_encouragement_stream` - Get streaming encouragement
- `POST /generate_idea_stream` - Get streaming creative ideas

## Configuration

### Google Cloud Vision API
1. Create a Google Cloud project
2. Enable the Vision API
3. Create a service account and download the JSON key
4. Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable

### LM Studio (Optional)
1. Install LM Studio
2. Download a compatible model (e.g., Llama 3.1 8B)
3. Start the local server on `localhost:1234`
4. The app will automatically connect for AI suggestions

## Development

### Adding New Block Types
Edit `static/blocks_map.json` to add new micro:bit blocks to the recognition system.

### Customizing AI Suggestions
Modify the prompt templates in `app.py` to adjust the AI's feedback style and suggestions.

### Testing
The app includes comprehensive error handling and fallback mechanisms for when external services are unavailable.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is open source and available under the [MIT License](LICENSE).

## Acknowledgments

- Built for educational purposes to help students learn micro:bit programming
- Integrates with Google Cloud Vision API for image recognition
- Uses LM Studio for local AI processing
- Inspired by the need for accessible programming education tools

## Support

For questions or issues, please open an issue on GitHub or contact the development team.

---

**Happy Coding!** 🚀
