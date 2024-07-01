import random
import telebot
import os
import psycopg2
from datetime import datetime

# Connect to DB
con = psycopg2.connect(
   database="postgres",
   user=os.environ['PG_USER'],
   password=os.environ['PG_PASSWORD'],
   host=os.environ['PG_HOST'],
   port=os.environ['PG_PORT']
)

cursor = con.cursor()


# Connect to Telegram BOT
bot = telebot.TeleBot(os.environ['API_TOKEN'], allow_sending_without_reply=True)

command = [telebot.types.BotCommand("start", "Help information"),
           telebot.types.BotCommand("help", "Help information"),
           telebot.types.BotCommand("football", "/football 21.06 21:30 Матч Арена"),
           telebot.types.BotCommand("leaderboard", "Show current leaderboard")]

bot.set_my_commands(command)


# Handle '/start' and '/help'
@bot.message_handler(commands=['help', 'start'])
def send_welcome(message):
    bot.reply_to(message,
"""
Этот бот позволяет собирать составы для игры в футбол.

❔ Как начать сбор футбола?
Запусти команду /football с форматированием как в подсказке.

🐛 Нашел баг? Напиши в ЛС @aqquila
            
""")


# Handle callbacks
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call:telebot.types.CallbackQuery):
    try:
        if 'Собираем футбол!' in call.message.text:
            game_id = get_game_id(call.message.chat.id, call.message.id)
            participant_list = get_list_participants(game_id)
            is_user_in_participant_list = call.from_user.id in [row[0] for row in participant_list if not(row[1])]
            original_message = call.message.text.split('\n\nСписок участников:')[0] + '\n\nСписок участников:'
            if call.data == '+':
                if is_user_in_participant_list:
                    bot.send_message(call.message.chat.id, 'Ты уже в списке участников, бро')
                else:
                    add_participant_to_game(datetime.now(), game_id, call.from_user.id, False)
            elif call.data == '-' and is_user_in_participant_list:
                remove_participant_from_game(game_id, call.from_user.id, False)
            elif call.data == '+1':
                add_participant_to_game(datetime.now(), game_id, call.from_user.id, True)
            elif call.data == '-1':
                remove_participant_from_game(game_id, call.from_user.id, True)
            elif call.data == 'gen_teams':
                team_1, team_2 = generate_teams(participant_list, game_id)
                markup = telebot.types.InlineKeyboardMarkup()
                button_shuffle_teams = telebot.types.InlineKeyboardButton(text='Перемешать составы', callback_data='reshuffle')
                button_confirm_teams = telebot.types.InlineKeyboardButton(text='Закрепить составы', callback_data='confirm_squads')
                markup.row(button_shuffle_teams)
                markup.row(button_confirm_teams)
                message_txt = generate_teams_message(team_1, team_2, call.message.chat.id, game_id)
                bot.send_message(chat_id=call.message.chat.id, text=message_txt, reply_markup=markup)
            participant_list = get_list_participants(game_id)
            new_message = generate_gathering_squad_message(original_message, participant_list, call.message.chat.id)
            bot.edit_message_text(text=new_message, chat_id=call.message.chat.id, message_id=call.message.id, reply_markup=call.message.reply_markup)
        elif 'Составы на игру' in call.message.text:
            game_id = int([token for token in call.message.text.split(' ') if '№' in token][0].replace('№', ''))
            if call.data == 'reshuffle':
                participant_list = get_list_participants(game_id)
                team_1, team_2 = generate_teams(participant_list, game_id)
                message_txt = generate_teams_message(team_1, team_2, call.message.chat.id, game_id)
                bot.edit_message_text(text=message_txt, chat_id=call.message.chat.id, message_id=call.message.id, reply_markup=call.message.reply_markup)
            if call.data == 'confirm_squads':
                markup = telebot.types.InlineKeyboardMarkup()
                button_team_1_win = telebot.types.InlineKeyboardButton(text='Победа Snow Kids', callback_data='win_team_1')
                button_team_2_win = telebot.types.InlineKeyboardButton(text='Победа Shadows', callback_data='win_team_2')
                button_draw = telebot.types.InlineKeyboardButton(text='Ничья', callback_data='draw')
                markup.row(button_team_1_win)
                markup.row(button_team_2_win)
                markup.row(button_draw)
                bot.edit_message_text(text=call.message.text, chat_id=call.message.chat.id, message_id=call.message.id, reply_markup=markup)
            if call.data == 'win_team_1':
                bot.edit_message_text(text=call.message.text, chat_id=call.message.chat.id, message_id=call.message.id)
                photo = open('img/snow_kids.jpg', 'rb')
                bot.send_photo(chat_id=call.message.chat.id, photo=photo, caption='Поздравляем команду Snow Kids с победой!')
                add_result_to_participant(game_id, 1, 1)
                add_result_to_participant(game_id, 2, 2)
            if call.data == 'win_team_2':
                bot.edit_message_text(text=call.message.text, chat_id=call.message.chat.id, message_id=call.message.id)
                photo = open('img/shadows.jpg', 'rb')
                bot.send_photo(chat_id=call.message.chat.id, photo=photo, caption='Поздравляем команду Shadows с победой!')
                add_result_to_participant(game_id, 1, 2)
                add_result_to_participant(game_id, 2, 1)
            if call.data == 'draw':
                bot.edit_message_text(text=call.message.text, chat_id=call.message.chat.id, message_id=call.message.id)
                photo = open('img/draw.jpg', 'rb')
                bot.send_photo(chat_id=call.message.chat.id, photo=photo, caption='Ничья! Ну и напряженная игра выдалась...')
                add_result_to_participant(game_id, 1, 3)
                add_result_to_participant(game_id, 2, 3)
    except Exception as e:
        print(e)


# Handle '/football'
@bot.message_handler(commands=['football'])
def send_start_gathering_football(message:telebot.types.Message):
    try:
        markup = telebot.types.InlineKeyboardMarkup()
        button_check_in = telebot.types.InlineKeyboardButton(text='Записаться', callback_data='+')
        button_check_out = telebot.types.InlineKeyboardButton(text='Отписаться', callback_data='-')
        button_check_in_friend = telebot.types.InlineKeyboardButton(text='Записать друга', callback_data='+1')
        button_check_out_friend = telebot.types.InlineKeyboardButton(text='Отписать друга', callback_data='-1')
        button_generate_teams = telebot.types.InlineKeyboardButton(text='Сгенерировать составы', callback_data='gen_teams')
        markup.row(button_check_in, button_check_out)
        markup.row(button_check_in_friend, button_check_out_friend)
        markup.row(button_generate_teams)
        message_tokens = message.text.split(' ')
        message_tokens.pop(0)
        date = message_tokens[0]
        time = message_tokens[1]
        place = ' '.join(message_tokens[2:])
        final_message_txt = "Собираем футбол! \nДата: {0}\nВремя: {1}\nПоле: {2}\n\nСписок участников:".format(date, time, place)
        final_message = bot.send_message(message.chat.id, final_message_txt, reply_markup=markup)
        game_created_at = datetime.fromtimestamp(final_message.date)
        game_start_at_txt = "{0}.{1} {2}".format(date, game_created_at.year, time)
        game_start_at_dt = datetime.strptime(game_start_at_txt, "%d.%m.%Y %H:%M")
        cursor.execute("insert into game(created_at, tg_chat_id, tg_message_id, start_at, place_nm) values ('{0}', {1}, {2}, '{3}', '{4}')".format(game_created_at, final_message.chat.id, final_message.id, game_start_at_dt, place))
        con.commit()
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, 'Неверное форматирование')


@bot.message_handler(commands=['leaderboard'])
def send_leaderboard(message:telebot.types.Message):
    leaderboard_export = get_leaderboard(message.chat.id)
    message_txt = "Таблица лидеров:\n"
    for i, leaderboard_export_row in enumerate(leaderboard_export):
        chat_member = bot.get_chat_member(message.chat.id, leaderboard_export_row[0])
        tg_first_name = chat_member.user.first_name if chat_member.user.first_name else ''
        tg_last_name = chat_member.user.last_name if chat_member.user.last_name else ''
        tg_nickname = '@' + chat_member.user.username
        message_txt += "\n{0}. {1} {2}({3}): {4} points ({5} games)".format(i+1, tg_first_name, tg_last_name, tg_nickname, leaderboard_export_row[1], leaderboard_export_row[2])
    bot.send_message(message.chat.id, message_txt)


def get_list_participants(game_id:int):
    try:
        cursor.execute("""
        select gp.tg_chat_member_id, is_plus_one
        from game_participant gp
            join game g 
                on gp.game_id = g.id 
                    and g.id = {0}
        order by gp.created_at""".format(game_id))
    except Exception as e:
        return []
    return cursor.fetchall()


def generate_gathering_squad_message(message:str, participant_list:list, chat_id:int):
    new_message = message
    for i, participant in enumerate(participant_list):
        chat_member = bot.get_chat_member(chat_id, participant[0])
        tg_first_name = chat_member.user.first_name if chat_member.user.first_name else ''
        tg_last_name = chat_member.user.last_name if chat_member.user.last_name else ''
        tg_nickname = '@' + chat_member.user.username
        is_plus_one = '(+1)' if participant[1] else ''
        new_message += "\n{0}. {1} {2} ({3}) {4}".format(i+1, tg_first_name, tg_last_name, tg_nickname, is_plus_one)
    return new_message


def generate_teams_message(team_1:list, team_2:list, chat_id:int, game_id:int):
    new_message = "Составы на игру №{0} \n\n".format(game_id)
    new_message += "Team Snow Kids:"
    for i, participant in enumerate(team_1):
        chat_member = bot.get_chat_member(chat_id, participant[0])
        tg_first_name = chat_member.user.first_name if chat_member.user.first_name else ''
        tg_last_name = chat_member.user.last_name if chat_member.user.last_name else ''
        tg_nickname = '@' + chat_member.user.username
        is_plus_one = '(+1)' if participant[1] else ''
        new_message += "\n{0}. {1} {2} ({3}) {4}".format(i+1, tg_first_name, tg_last_name, tg_nickname, is_plus_one)
    new_message += "\n\nTeam Shadows:"
    for i, participant in enumerate(team_2):
        chat_member = bot.get_chat_member(chat_id, participant[0])
        tg_first_name = chat_member.user.first_name if chat_member.user.first_name else ''
        tg_last_name = chat_member.user.last_name if chat_member.user.last_name else ''
        tg_nickname = '@' + chat_member.user.username
        is_plus_one = '(+1)' if participant[1] else ''
        new_message += "\n{0}. {1} {2} ({3}) {4}".format(i+1, tg_first_name, tg_last_name, tg_nickname, is_plus_one)
    return new_message


def generate_teams(participant_list:list, game_id:int):
    clear_participants_team(game_id)
    team_1 = []
    team_2 = []
    shuffled_participant_list = participant_list.copy()
    random.shuffle(shuffled_participant_list)
    for i, participant in enumerate(shuffled_participant_list):
        if i % 2 == 0:
            team_1.append(participant)
            add_participant_to_team(game_id, participant[0], participant[1], 1)
        else:
            team_2.append(participant)
            add_participant_to_team(game_id, participant[0], participant[1], 2)
    return team_1, team_2


def get_game_id(chat_id, message_id):
    cursor.execute("""
    select id
    from game 
    where tg_chat_id = {0} and tg_message_id = {1}
    """.format(chat_id, message_id))
    return [row[0] for row in cursor.fetchall()][0]


def add_participant_to_game(created_at:datetime, game_id:int, tg_chat_member_id:int, is_plus_one:bool):
    cursor.execute("""
    insert into game_participant(created_at, game_id, tg_chat_member_id, is_plus_one) 
    values ('{0}', {1}, {2}, {3})
    """.format(created_at, game_id, tg_chat_member_id, is_plus_one))
    con.commit()


def remove_participant_from_game(game_id:int, tg_chat_member_id:int, is_plus_one:bool):
    cursor.execute("""
    delete from game_participant 
    where game_id = {0} and tg_chat_member_id = {1} and is_plus_one = {2}
        and id = (select max(id) from game_participant where game_id = {0} and tg_chat_member_id = {1} and is_plus_one = {2})
    """.format(game_id, tg_chat_member_id, is_plus_one))
    con.commit()


def add_participant_to_team(game_id:int, tg_chat_member_id:int, is_plus_one:bool, team_id:int):
    cursor.execute("""
    update game_participant
    set team_id = {3}
    where game_id = {0} and tg_chat_member_id = {1} and is_plus_one = {2} and team_id is null
        and id = (select max(id) from game_participant where game_id = {0} and tg_chat_member_id = {1} and is_plus_one = {2} and team_id is null)
    """.format(game_id, tg_chat_member_id, is_plus_one, team_id))
    con.commit()


def clear_participants_team(game_id:int):
    cursor.execute("""
    update game_participant
    set team_id = NULL
    where game_id = {0} 
    """.format(game_id))
    con.commit()


def add_result_to_participant(game_id:int, team_id:int, game_result_id:int):
    cursor.execute("""
    update game_participant
    set game_result_id = {2}
    where game_id = {0} and team_id = {1}
    """.format(game_id, team_id, game_result_id))
    con.commit()


def get_leaderboard(tg_chat_id:int):
    cursor.execute("""
    select 
	    gp.tg_chat_member_id,
	    sum(case 
	    		when game_result_id = 1 then 3
	    		when game_result_id = 2 then 0
	    		when game_result_id = 3 then 1
	    end) as points_amt,
	    count(distinct case when gp.game_result_id is not null then g.id end) as games_cnt
    from game_participant gp 
    	join game g 
    		on gp.game_id = g.id 
    where g.tg_chat_id = {0} and is_plus_one is false
    group by gp.tg_chat_member_id
    order by points_amt desc, games_cnt desc
    limit 10
    """.format(tg_chat_id))
    return cursor.fetchall()


bot.infinity_polling()
