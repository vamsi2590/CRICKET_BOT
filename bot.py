import pytz
import tzlocal
import uuid
import logging
import asyncio
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes,
)
import requests
from bs4 import BeautifulSoup
from io import BytesIO
import random
import time

# =============================================
# CONFIGURATION AND SETUP
# =============================================

# Force local timezone for your app
tzlocal.get_localzone = lambda: pytz.timezone('Asia/Kolkata')

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # DEBUG level for full trace
)
logger = logging.getLogger(__name__)

# List of channels to broadcast to (add your channel IDs/usernames)
BROADCAST_CHANNELS = [
    "@testing_demos"
]

# =============================================
# BROADCAST FUNCTIONS
# =============================================

async def broadcast_message(context: ContextTypes.DEFAULT_TYPE, message: str, parse_mode='Markdown'):
    """Send a message to all broadcast channels instantly"""
    tasks = []
    for channel in BROADCAST_CHANNELS:
        try:
            task = context.bot.send_message(
                chat_id=channel,
                text=message,
                parse_mode=parse_mode
            )
            tasks.append(task)
        except Exception as e:
            logger.error(f"Failed to send to {channel}: {e}")
    await asyncio.gather(*tasks, return_exceptions=True)

async def broadcast_photo(context: ContextTypes.DEFAULT_TYPE, photo, caption=None):
    """Send a photo to all broadcast channels instantly"""
    tasks = []
    for channel in BROADCAST_CHANNELS:
        try:
            task = context.bot.send_photo(
                chat_id=channel,
                photo=photo,
                caption=caption,
                parse_mode='Markdown'
            )
            tasks.append(task)
        except Exception as e:
            logger.error(f"Failed to send photo to {channel}: {e}")
    await asyncio.gather(*tasks, return_exceptions=True)

# =============================================
# UTILITY FUNCTIONS (KEEP ALL YOUR EXISTING FUNCTIONS)
# =============================================
# [Keep all your existing utility functions exactly as they are]
# [Keep all your existing data scraping functions exactly as they are]

# =============================================
# UTILITY FUNCTIONS
# =============================================

def generate_odds_image(data):
    """Generate image with team odds and projections in horizontal layout"""
    # Filter out empty sections
    valid_sections = []
    
    # Team odds section
    if data.get('odds'):
        for team, odds in data['odds'].items():
            if len(odds) >= 2:
                valid_sections.append({
                    "label": team[:10],  # Limit team name length
                    "values": [odds[0], odds[1]],
                    "underline": True
                })
                break
    
    # Over projections sections
    if data.get('over_projections'):
        for proj in data['over_projections']:
            if proj.get('yes_odds') != 'N/A' and proj.get('no_odds') != 'N/A':
                valid_sections.append({
                    "label": proj['title'],
                    "values": [proj['no_odds'], proj['yes_odds']]
                })
    
    if not valid_sections:
        return None
    
    # Calculate required image size
    num_sections = len(valid_sections)
    section_height = 70
    padding_top = 25
    padding_bottom = 25
    total_height = padding_top + (num_sections * section_height) + padding_bottom
    
    # Font settings
    try:
        font_label = ImageFont.truetype("arialbd.ttf", 24)
        font_value = ImageFont.truetype("arial.ttf", 20)
    except:
        font_label = ImageFont.load_default()
        font_value = ImageFont.load_default()
    
    # Calculate required width
    max_label_width = max(font_label.getlength(s["label"]) for s in valid_sections) + 20
    box_width = 70
    total_width = int(max_label_width + 2 * box_width + 100)  # +100 for spacing
    
    # Create image
    img = Image.new('RGB', (total_width, total_height), color=(35, 35, 35))
    draw = ImageDraw.Draw(img)
    
    # Drawing parameters
    box_height = 35
    radius = 5
    text_padding = 8
    y_position = padding_top
    line_thickness = 2
    
    for section in valid_sections:
        x_position = 20
        
        # Draw label
        draw.text((x_position, y_position), 
                 section["label"], 
                 font=font_label, 
                 fill=(220, 220, 220))
        x_position += max_label_width
        
        # Left box (red)
        draw.rounded_rectangle(
            [(x_position, y_position), 
             (x_position + box_width, y_position + box_height)],
            radius=radius, 
            fill=(60, 0, 0), 
            outline=(255, 50, 50)
        )
        draw.text(
            (x_position + text_padding, y_position + text_padding),
            section["values"][0],
            font=font_value,
            fill=(255, 200, 200)
        )
        x_position += box_width + 20
        
        # Right box (green)
        draw.rounded_rectangle(
            [(x_position, y_position), 
             (x_position + box_width, y_position + box_height)],
            radius=radius, 
            fill=(0, 60, 0), 
            outline=(50, 255, 50)
        )
        draw.text(
            (x_position + text_padding, y_position + text_padding),
            section["values"][1],
            font=font_value,
            fill=(200, 255, 200)
        )
        
        # Draw white line under team odds section if specified
        if section.get("underline"):
            line_y = y_position + box_height + 10
            draw.line(
                [(20, line_y), (total_width - 20, line_y)],
                fill=(255, 255, 255),
                width=line_thickness
            )
            y_position += 15  # Extra space after line
        
        y_position += section_height
    
    # Convert to bytes for Telegram
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return img_byte_arr


# =============================================
# DATA SCRAPING FUNCTIONS
# =============================================

def get_live_matches():
    """Fetch all currently live matches from crex.com"""
    base_url = "https://crex.com"
    headers = {"User-Agent": "Mozilla/5.0"}
    matches = []
    
    try:
        response = requests.get(base_url, headers=headers)
        response.raise_for_status()
        logger.debug("Fetched live matches page successfully")
        
        soup = BeautifulSoup(response.text, "html.parser")
        match_cards = soup.find_all("a", href=True)

        for card in match_cards:
            match_info = card.find("h3", class_="match-number")
            if not match_info:
                continue
                
            # Extract match basic info
            match_number = match_info.contents[0].strip()
            venue_spans = match_info.find_all("span")
            venue = venue_spans[-1].get_text(strip=True) if venue_spans else "N/A"
            
            # Extract team information
            teams = card.find_all("div", class_="team-score")
            if len(teams) < 2:
                continue

            def safe_text(el, tag, cls):
                """Helper to safely extract text from elements"""
                t = el.find(tag, class_=cls)
                return t.text.strip() if t else "Yet to bat"

            team1 = teams[0]
            team2 = teams[1]

            team1_name = safe_text(team1, "span", "live-c")
            team1_score = safe_text(team1, "span", "match-score")
            team1_overs = safe_text(team1, "span", "match-over")

            team2_name = safe_text(team2, "span", "live-d")
            team2_score = safe_text(team2, "span", "match-score")
            team2_overs = safe_text(team2, "span", "match-over")

            def not_started(score, overs):
                """Check if match hasn't started yet"""
                return score in ["Yet to bat", "", None] or overs.strip().startswith("0") or overs.strip() == ""

            # Skip matches that haven't started
            if not_started(team1_score, team1_overs) and not_started(team2_score, team2_overs):
                continue

            # Get match status
            comment = card.find("span", class_="comment")
            status = comment.text.strip() if comment else "Live"

            # Build match URL
            relative_url = card["href"]
            full_url = base_url + relative_url

            matches.append({
                "match": match_number,
                "venue": venue,
                "team1": team1_name,
                "team1_score": team1_score,
                "team1_overs": team1_overs,
                "team2": team2_name,
                "team2_score": team2_score,
                "team2_overs": team2_overs,
                "status": status,
                "url": full_url,
            })
            
        logger.debug(f"Parsed {len(matches)} live matches")
    except Exception as e:
        logger.error(f"Error getting live matches: {e}")
        return {"error": str(e)}

    return {"matches": matches}


def get_match_summary(url):
    """Get detailed summary of a specific match"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    data = []
    ball_events = []  # Stores all ball events in sequence
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        logger.debug(f"Fetched match summary from {url}")
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract team names
        team1 = soup.select_one(".team-name.team-1")
        team1 = team1.text.strip() if team1 else "N/A"

        # Extract score and overs
        score_tag = soup.select_one(".team-score .runs span:nth-of-type(1)")
        over_tag = soup.select_one(".team-score .runs span:nth-of-type(2)")
        score = score_tag.text.strip() if score_tag else "N/A"
        overs = over_tag.text.strip() if over_tag else "N/A"

        # Extract match status
        status_tag = soup.find("div", class_="final-result") or soup.find("div", class_="comment")
        match_status = status_tag.text.strip() if status_tag else "N/A"

        # Extract CRR and RRR
        crr, rrr = "N/A", "YET TO BAT"
        for span in soup.find_all("span", class_="title"):
            if "CRR" in span.text:
                val = span.find("span", class_="data")
                if val:
                    crr = val.text.strip()
            if "RRR" in span.text:
                val = span.find("span", class_="data")
                if val:
                    rrr = val.text.strip()

        # Extract partnership info
        pship_tag = soup.select_one(".p-ship span:nth-of-type(2)")
        partnership = pship_tag.text.strip() if pship_tag else "N/A"

        # Extract last wicket info
        lw_tag = soup.select_one(".l-wicket")
        last_wkt = lw_tag.text.strip() if lw_tag else "N/A"

        # Extract ball-by-ball events
        result_container = soup.select(".result-box span")
        for tag in result_container:
            text = tag.get_text(strip=True)
            if text:  # Only add if there's actual text
                ball_events.append(text)

        # Organize data with clear separation
        data.append({
            "basic_info": {
                "Team": team1,
                "Score": f"{score} ({overs})",
            },
            "rates": {
                "CRR": crr,
                "RRR": rrr,
            },
            "match_state": {
                "Partnership": partnership,
                "Last Wicket": last_wkt,
                "Status": match_status,
            },
            "ball_events": ball_events  # All ball events in sequence
        })
        
        logger.debug("Match summary parsed successfully")
    except Exception as e:
        logger.error(f"Error getting match summary: {e}")
        return {"error": str(e)}

    return data


def get_player_stats(url):
    """Get detailed player statistics for a match"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        logger.debug(f"Fetched player stats from {url}")
        soup = BeautifulSoup(response.text, 'html.parser')

        batting_players = []
        bowling_players = []
        striker_data = {}

        # Extract batting information (first two blocks)
        batting_blocks = soup.find_all('div', class_='batsmen-partnership')[:2]

        for player in batting_blocks:
            # Extract basic batting info
            name = player.find('div', class_='batsmen-name').get_text(strip=True)
            score_text = player.find('div', class_='batsmen-score').get_text(' ', strip=True)
            score_parts = score_text.split()
            
            runs = score_parts[0] if len(score_parts) > 0 else '0'
            balls = score_parts[1].strip('()') if len(score_parts) > 1 else '0'

            # Extract detailed stats
            stats_div = player.find('div', class_='player-strike-wrapper')
            fours = sixes = sr = 'N/A'
            if stats_div:
                spans = stats_div.find_all('span')
                if len(spans) >= 6:
                    fours = spans[1].get_text(strip=True)
                    sixes = spans[3].get_text(strip=True)
                    sr = spans[5].get_text(strip=True)

            # Check if this is the striker
            is_striker = bool(player.find('div', class_='circle-strike-icon'))

            player_data = {
                "name": name,
                "runs": runs,
                "balls": balls,
                "fours": fours,
                "sixes": sixes,
                "strike_rate": sr,
                "on_strike": is_striker
            }

            batting_players.append(player_data)

            if is_striker:
                striker_data = player_data

        # Extract bowling information (next two blocks)
        bowling_blocks = soup.find_all('div', class_='batsmen-partnership')[2:4]

        for player in bowling_blocks:
            name = player.find('div', class_='batsmen-name').get_text(strip=True)
            score_text = player.find('div', class_='batsmen-score').get_text(' ', strip=True)
            score_parts = score_text.split()

            # Parse bowling figures (format: wickets-runs)
            figures = score_parts[0] if len(score_parts) > 0 else '0-0'
            overs = score_parts[1].strip('()') if len(score_parts) > 1 else '0'
            
            if '-' in figures:
                wkts, runs = figures.split('-')
            else:
                wkts, runs = ('0', '0')

            # Extract economy rate
            econ = player.find('span', string=' Econ: ')
            econ_val = econ.find_next_sibling('span').get_text(strip=True) if econ else 'N/A'

            bowling_players.append({
                "name": name,
                "overs": overs,
                "runs_conceded": runs,
                "wickets": wkts,
                "economy": econ_val
            })

        logger.debug("Player stats parsed successfully")
        return {
            "batting": batting_players,
            "bowling": bowling_players,
            "striker": striker_data
        }

    except Exception as e:
        logger.error(f"Error getting player stats: {e}")
        return {"error": str(e)}


def get_match_odds(url):
    """Get betting odds and projections for a match"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    result = {
        "win_probabilities": {},
        "odds": {},
        "over_projections": []
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        logger.debug(f"Fetched match odds from {url}")
        soup = BeautifulSoup(response.text, 'html.parser')

        # Win Probabilities
        prob_view = soup.find('div', class_='progressBarWrapper')
        if prob_view:
            team_divs = prob_view.find_all('div', class_='teamName')
            if len(team_divs) >= 2:
                team1_name = team_divs[0].find('div').get_text(strip=True)
                team1_prob = team_divs[0].find_all('div')[-1].get_text(strip=True)
                team2_name = team_divs[1].find('div').get_text(strip=True)
                team2_prob = team_divs[1].find_all('div')[-1].get_text(strip=True)

                result["win_probabilities"] = {
                    team1_name: team1_prob,
                    team2_name: team2_prob
                }

        # Odds
        odds_view = soup.find('div', class_='oddSessionInProgress')
        if odds_view:
            divs = odds_view.find_all('div')
            if len(divs) >= 2:
                team_name = divs[0].get_text(strip=True)
                odds = [div.get_text(strip=True) for div in divs[1:]]
                result["odds"][team_name] = odds

        # Over Projections
        projections = soup.find_all('div', class_='displayFlex')
        for proj in projections:
            title = proj.find('div', class_='overRunText')
            if title:
                title_text = title.get_text(strip=True)
                yes_no = proj.find('div', class_='yes-no-odds')
                if yes_no:
                    no_odds = yes_no.find('div', class_='no')
                    yes_odds = yes_no.find('div', class_='yes')

                    if no_odds and yes_odds:
                        no_odds_text = no_odds.find_all('span')[-1].get_text(strip=True) if no_odds.find_all('span') else 'N/A'
                        yes_odds_text = yes_odds.find_all('span')[-1].get_text(strip=True) if yes_odds.find_all('span') else 'N/A'

                        result["over_projections"].append({
                            "title": title_text,
                            "yes_odds": yes_odds_text,
                            "no_odds": no_odds_text
                        })

        logger.debug("Match odds parsed successfully")

    except Exception as e:
        logger.error(f"Error getting match odds: {e}")
        return {"error": str(e)}

    return result



# =============================================
# TELEGRAM BOT HANDLERS (UPDATED FOR BROADCAST)
# =============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command"""
    logger.info(f"User {update.effective_user.id} started the bot")
    await update.message.reply_text(
        "🏏 *Welcome to Crex Cricket Live Bot!*\n\n"
        "Use /matches to see live matches and subscribe to ball-by-ball updates.",
        parse_mode='Markdown'
    )

async def show_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /matches command - shows live matches"""
    logger.info(f"User {update.effective_user.id} requested live matches")
    
    matches_data = get_live_matches()

    if isinstance(matches_data, dict) and "error" in matches_data:
        await update.message.reply_text("⚠️ Error fetching matches. Try again later.")
        return

    matches = matches_data.get("matches", [])

    if not matches:
        await update.message.reply_text("🚫 No live matches currently available")
        return

    context.user_data['matches'] = matches

    keyboard = []
    for i, match in enumerate(matches):
        btn_text = f"{match['team1']} vs {match['team2']} - {match['status']}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=str(i))])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('🔴 Live Matches - Select one:', reply_markup=reply_markup)

# Track last sent events per match (for all channels)
last_sent_events = {}
last_sent_odds = {}

async def send_ball_by_ball_update(context: ContextTypes.DEFAULT_TYPE):
    """Job function to send regular ball-by-ball updates to all channels"""
    job = context.job
    match_url = job.data['match_url']
    logger.debug(f"Sending ball-by-ball update for match {match_url}")

    try:
        # Fetch all match data
        summary = get_match_summary(match_url)
        players = get_player_stats(match_url)
        odds = get_match_odds(match_url)

        if not summary or not players or not odds:
            logger.warning("One or more data sources returned empty or error")
            await broadcast_message(context, "⚠️ Failed to fetch match data.")
            return

        # Handle odds image (send every 50 seconds if changed)
        now = time.time()
        if odds != last_sent_odds.get(match_url) and (now - last_sent_odds.get(f"{match_url}_time", 0) > 50):
            img_buffer = generate_odds_image(odds)
            if img_buffer:
                await broadcast_photo(context, img_buffer)
                last_sent_odds[match_url] = odds
                last_sent_odds[f"{match_url}_time"] = now

        ball_events = summary[0].get('ball_events', [])
        if not ball_events:
            logger.debug("No ball events to send")
            return

        # Get current over info
        try:
            current_over = summary[0]['basic_info']['Score'].split('(')[1].split(')')[0]
            over_parts = current_over.split('.')
            over_number = int(over_parts[0])
            ball_in_over = int(over_parts[1]) if len(over_parts) > 1 else 0
        except Exception as e:
            logger.warning(f"Error parsing overs: {e}")
            over_number = 0
            ball_in_over = 0

        # Determine new events to send
        last_event = last_sent_events.get(match_url)
        last_over_sent = last_sent_events.get(f"{match_url}_over", -1)

        if last_event and last_event in ball_events:
            last_index = ball_events.index(last_event)
            new_events = ball_events[last_index + 1:]
        else:
            new_events = ball_events

        if not new_events:
            logger.debug("No new ball events to send")
            return

        # Process and broadcast each new ball event
        for event in new_events:
            logger.debug(f"Broadcasting ball event: {event}")
            await broadcast_message(context, f"{event}")

            # Send score line
            await broadcast_message(context, f"🥎 *{summary[0]['basic_info']['Score']}🥎*")

            # Handle special event messages
            event_upper = event.upper()
            if "4" in event_upper:
                four_msgs = [
                    "💥 *FOUR!* Cracked through the covers!",
                    "🔥 *FOUR!* Beautiful timing!",
                    "🏏 *FOUR!* Pierced the field perfectly!",
                    "💨 *FOUR!* Raced to the boundary!",
                    "📐 *FOUR!* Pure placement brilliance!"
                ]
                await broadcast_message(context, random.choice(four_msgs))

            elif "6" in event_upper:
                six_msgs = [
                    "🚀 *SIX!* Into the stands!",
                    "🌪️ *SIX!* That went miles!",
                    "💣 *SIX!* Smashed with power!",
                    "🪁 *SIX!* High and handsome!",
                    "🔨 *SIX!* Clean hit, maximum!"
                ]
                await broadcast_message(context, random.choice(six_msgs))

            elif "OUT" in event_upper or "WICKET" in event_upper:
                wicket_msgs = [
                    "💀 *WICKET!* Gone!",
                    "🎯 *WICKET!* Clean bowled!",
                    "🧤 *WICKET!* Taken behind!",
                    "🔁 *WICKET!* Caught at the ropes!",
                    "💔 *WICKET!* Big blow!"
                ]
                await broadcast_message(context, random.choice(wicket_msgs))

            # Send striker info
            striker = players.get('striker')
            if striker and striker.get('name') != 'N/A':
                striker_msg = f" {striker['name']} {striker['runs']}({striker['balls']}) on strike ✔️"
                await broadcast_message(context, striker_msg)

            # Send "last ball of over" notification
            if ball_in_over == 5:
                await broadcast_message(context, "*Last ball of over*")

            # Send match summary if new over
            if over_number != last_over_sent:
                await broadcast_message(
                    context,
                    f"*CRR*: {summary[0]['rates']['CRR']} | *RRR*: {summary[0]['rates']['RRR']}"
                )
                if summary[0]['match_state'].get('Partnership') != 'N/A':
                    await broadcast_message(
                        context,
                        f"*Partnership*: {summary[0]['match_state']['Partnership']}"
                    )
                if summary[0]['match_state'].get('Last Wicket') != 'N/A':
                    await broadcast_message(
                        context,
                        f"{summary[0]['match_state']['Last Wicket']} ❌ "
                    )
                await broadcast_message(
                    context,
                    f"⚠️ {summary[0]['match_state']['Status']}"
                )
                last_sent_events[f"{match_url}_over"] = over_number

        # Update last sent ball event
        last_sent_events[match_url] = new_events[-1]

    except Exception as e:
        logger.error(f"Error in ball-by-ball update job: {e}")
        await broadcast_message(context, "⚠️ Error fetching ball-by-ball update.")

async def subscribe_to_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for match selection - starts updates"""
    query = update.callback_query
    index_str = query.data if query else None
    logger.info(f"User {update.effective_user.id} subscribed to match index: {index_str}")
    
    if index_str is None:
        await query.answer()
        await query.edit_message_text("❌ Match URL not found.")
        return

    matches = context.user_data.get('matches', [])
    try:
        index = int(index_str)
        match_url = matches[index]['url']
    except (ValueError, IndexError):
        await query.answer()
        await query.edit_message_text("❌ Invalid match selected.")
        return

    # Remove any existing update jobs for this match
    current_jobs = context.job_queue.get_jobs_by_name(match_url)
    for job in current_jobs:
        job.schedule_removal()
        logger.debug(f"Removed existing job for match {match_url}")

    # Schedule new updates job
    context.job_queue.run_repeating(
        send_ball_by_ball_update,
        interval=1,  # Check every 1 second
        first=0,     # Start immediately
        name=match_url,
        data={'match_url': match_url}
    )
    logger.info(f"Scheduled ball-by-ball updates for match {match_url}")

    await query.answer()
    await query.edit_message_text("✅ Subscribed to ball-by-ball live updates!")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /stop command - cancels updates"""
    chat_id = update.effective_chat.id
    
    # Find and remove all jobs this user started
    removed = 0
    for job in context.job_queue.jobs():
        if job.data.get('chat_id') == chat_id:
            job.schedule_removal()
            removed += 1
    
    if removed > 0:
        await update.message.reply_text(f"🔴 Stopped {removed} update streams")
    else:
        await update.message.reply_text("No active update streams to stop")

async def test_channel_message(update, context):
    """Test function for sending messages to channel"""
    try:
        await broadcast_message(context, "✅ Test message from bot to all channels!")
        await update.message.reply_text("Test message sent to all channels!")
    except Exception as e:
        await update.message.reply_text(f"Failed to send message to channels: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler for the bot"""
    logger.error(msg="Exception while handling update:", exc_info=context.error)

# =============================================
# BOT SETUP AND MAIN ENTRY POINT
# =============================================

def main():
    """Main function to configure and start the bot"""
    TOKEN = "8198311890:AAEEnGPIQN4XMXnzKHrrAkDXmLTQG_mod5Q"  # Your bot token

    # Create application and handlers
    application = ApplicationBuilder().token(TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("matches", show_matches))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("testchannel", test_channel_message))
    
    # Callback handler for match selection
    application.add_handler(CallbackQueryHandler(subscribe_to_match))
    
    # Error handler
    application.add_error_handler(error_handler)

    # Start polling
    logger.info("Starting bot polling...")
    application.run_polling()
    logger.info("Bot polling stopped.")

if __name__ == '__main__':
    main()