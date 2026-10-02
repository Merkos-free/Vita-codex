// OFFLINE UI / HARDWARE PROBE. No network transport or Codex dictation yet.
// Original source; not a fork of Vela or WoozyLLM. See docs/STATUS.md.
#include "ui_model.hpp"
#include "microphone.hpp"
#include "ime_text.hpp"
#include <vita2d.h>
#include <psp2/apputil.h>
#include <psp2/ctrl.h>
#include <psp2/common_dialog.h>
#include <psp2/kernel/threadmgr/callback.h>
#include <psp2/display.h>
#include <psp2/ime_dialog.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/power.h>
#include <psp2/touch.h>
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>

namespace {
const auto bg=RGBA8(8,12,18,255), panel=RGBA8(17,25,35,255),
    accent=RGBA8(22,186,245,255), text=RGBA8(237,243,249,255), muted=RGBA8(156,173,191,255),
    border=RGBA8(38,56,73,255), warn=RGBA8(246,192,95,255);
vita2d_pgf* font=nullptr;
cv::Model model;
MicrophoneProbe mic;
uint16_t ime_buffer[SCE_IME_DIALOG_MAX_TEXT_LENGTH+1]{};
bool ime_active=false;
std::vector<uint16_t> ime_initial, ime_title;
bool power_event_seen=false;
bool power_callback_ready=false;
int power_event(int, int, int, void*) {
    mic.stop(); power_event_seen=true; return 0;
}
int max_scroll=0;
std::string notice;
const char* titles[]={"Обзор","Чат","Файлы","Голос","Настройки"};
void label(float x,float y,const std::string& s,unsigned color=text,float scale=1.05f) {
    vita2d_pgf_draw_text(font,x,y,color,scale,s.c_str());
}
void box(cv::Rect r,unsigned color,int radius=10) {
    vita2d_draw_rectangle(r.x+radius,r.y,r.w-radius*2,r.h,color);
    vita2d_draw_rectangle(r.x,r.y+radius,r.w,r.h-radius*2,color);
    vita2d_draw_fill_circle(r.x+radius,r.y+radius,radius,color);
    vita2d_draw_fill_circle(r.x+r.w-radius,r.y+radius,radius,color);
    vita2d_draw_fill_circle(r.x+radius,r.y+r.h-radius,radius,color);
    vita2d_draw_fill_circle(r.x+r.w-radius,r.y+r.h-radius,radius,color);
}
int paragraph(const std::string& s,int y,unsigned color=muted) {
    auto lines=cv::wrap(s,850.0f,[](const auto& str){return vita2d_pgf_text_width(font,1.05f,str.c_str());});
    int top=y;
    for (const auto& line:lines) {
        if (y>=185 && y<=458) label(50,y,line,color);
        y+=29;
    }
    max_scroll=std::max(max_scroll,top+model.scroll+int(lines.size())*29-455);
    return y;
}
void begin_ime() {
    if (ime_active) return;
    std::memset(ime_buffer,0,sizeof ime_buffer);
    SceImeDialogParam p; sceImeDialogParamInit(&p);
    p.supportedLanguages=SCE_IME_LANGUAGE_ENGLISH|SCE_IME_LANGUAGE_RUSSIAN;
    p.languagesForced=SCE_FALSE;
    p.type=SCE_IME_DIALOG_TEXTBOX_MODE_DEFAULT;
    p.textBoxMode=SCE_IME_DIALOG_TEXTBOX_MODE_DEFAULT;
    ime_title=cv::to_ime("Черновик задания", SCE_IME_DIALOG_MAX_TITLE_LENGTH);
    ime_initial=cv::to_ime(model.draft, SCE_IME_DIALOG_MAX_TEXT_LENGTH);
    p.title=ime_title.data();
    p.initialText=ime_initial.data();
    p.dialogMode=SCE_IME_DIALOG_DIALOG_MODE_WITH_CANCEL;
    p.maxTextLength=SCE_IME_DIALOG_MAX_TEXT_LENGTH;
    p.inputTextBuffer=ime_buffer;
    int r=sceImeDialogInit(&p);
    if (r<0) notice="Не удалось открыть клавиатуру. Проверьте сборку на Vita.";
    else ime_active=true;
}
void poll_ime() {
    if (!ime_active || sceImeDialogGetStatus()!=SCE_COMMON_DIALOG_STATUS_FINISHED) return;
    SceImeDialogResult result{};
    const int status=sceImeDialogGetResult(&result);
    if (status>=0 && result.result>=0 && result.button==SCE_IME_DIALOG_BUTTON_ENTER) {
        model.draft=cv::utf16_to_utf8(ime_buffer,SCE_IME_DIALOG_MAX_TEXT_LENGTH);
        notice="Черновик сохранён в памяти. Не отправлен."; model.scroll=0;
    } else notice="Ввод отменён. Черновик сохранён без изменений.";
    sceImeDialogTerm(); ime_active=false;
    std::memset(ime_buffer,0,sizeof ime_buffer);
    std::fill(ime_initial.begin(),ime_initial.end(),0); ime_initial.clear();
}
void draw_screen() {
    vita2d_start_drawing(); vita2d_clear_screen();
    label(24,42,"< >  CODEX VITA",text,1.30f);
    label(420,40,"OFFLINE / UI PROTOTYPE",warn,0.95f);
    char b[24]; std::snprintf(b,sizeof b,"%d%%",scePowerGetBatteryLifePercent());
    label(869,40,b,muted,0.95f);
    for (int i=0;i<cv::screen_count;++i) {
        bool selected=i==int(model.screen);
        box(cv::tab_rect(i),selected?accent:panel);
        label(float(42+i*184),109,titles[i],selected?bg:text);
    }
    box(cv::content,panel);
    max_scroll=0;
    int y=190-model.scroll;
    switch(model.screen) {
        case cv::Screen::Overview:
            y=paragraph("Нативный клиент управления Codex",y,text);
            y=paragraph("Первый этап: интерфейс и локальная проверка ввода. Компьютер не подключён; проекты и результаты не выдумываются.",y+12);
            y=paragraph("Связь Vita с bridge ещё нужно реализовать и проверить. На ПК уже есть исходники bridge и автоматические тесты его протокола.",y+12);
            paragraph("L / R — вкладки. Touch — выбор вкладки. Up / Down — прокрутка.",y+12);
            break;
        case cv::Screen::Chat:
            y=paragraph("Черновик задания",y,text);
            y=paragraph(model.draft.empty()?"Нажмите X, чтобы проверить системную клавиатуру Vita. Текст пока не отправляется никуда.":model.draft,y+16,text);
            paragraph("X — редактировать черновик. Отправка отключена до подключения проверенного bridge.",y+18,warn);
            break;
        case cv::Screen::Files:
            y=paragraph("Изменения файлов",y,text);
            y=paragraph("Нет подключённой сессии. В этом экране не показывается синтетический diff как настоящий результат Codex.",y+12);
            paragraph("Будущий просмотр: весь экран под код, переключение файлов, увеличение текста. Изменения уже могут быть в рабочей папке: кнопки Apply здесь не будет.",y+12);
            break;
        case cv::Screen::Voice:
            y=paragraph("Встроенная диктовка Codex: ещё не проверена",y,text);
            y=paragraph("Это тест микрофона, НЕ распознавание. Обрабатывается один короткий блок звука, затем он стирается. Запись не сохраняется; сеть не используется.",y+12);
            y=paragraph("X — включить / остановить тест, не дольше 10 секунд. Отдельный платный API отсутствует.",y+12);
            if (model.scroll==0) {
                box({50,405,860,34},border,6);
                int w=int(mic.level()*848);
                if(w>0) vita2d_draw_rectangle(56,411,w,22,accent);
                label(50,473,mic.active()?"Микрофон активен":(mic.error()?"Ошибка микрофона — нужна проверка на устройстве":"Микрофон выключен"),mic.active()?accent:muted,0.9f);
            }
            break;
        case cv::Screen::Settings:
            y=paragraph("Параметры первого этапа",y,text);
            y=paragraph("Тема: тёмная. Рендер: VitaSDK + libvita2d. Разрешение: 960 x 544. Шрифт: системный, без поставки сторонних файлов шрифтов.",y+12);
            y=paragraph("Аккаунт OpenAI и ключи на Vita не сохраняются. Сетевое сопряжение в этом UI ещё не реализовано.",y+12);
            paragraph("Для соединения планируется HTTPS с проверкой сертификата и одноразовый PIN с экрана компьютера. Без кнопки отключения TLS-проверки.",y+12);
            break;
    }
    vita2d_draw_rectangle(0,488,960,56,bg);
    label(24,523,notice.empty()?"L/R вкладки   X действие   SELECT очистить   START выход":notice,muted,0.83f);
    vita2d_end_drawing();
    if(ime_active) vita2d_common_dialog_update();
    vita2d_swap_buffers();
    sceDisplayWaitVblankStart();
}
} // namespace
int main() {
    SceAppUtilInitParam init{}; SceAppUtilBootParam boot{};
    if (sceAppUtilInit(&init,&boot)<0) return 1;
    if(vita2d_init()<0) {sceAppUtilShutdown(); return 2;}
    SceCommonDialogConfigParam dialog_config{};
    sceCommonDialogSetConfigParam(&dialog_config);
    vita2d_set_clear_color(bg);
    font=vita2d_load_default_pgf();
    if(!font) {vita2d_fini(); sceAppUtilShutdown(); return 3;}
    sceCtrlSetSamplingMode(SCE_CTRL_MODE_ANALOG);
    sceTouchSetSamplingState(SCE_TOUCH_PORT_FRONT,SCE_TOUCH_SAMPLING_STATE_START);
    const SceUID power_cb=sceKernelCreateCallback("CodexVitaPower",0,power_event,nullptr);
    power_callback_ready=power_cb>=0 && scePowerRegisterCallback(power_cb)>=0;
    uint32_t previous=0; bool previous_touch=false, running=true;
    uint64_t next_scroll=0;
    while(running) {
        power_event_seen=false; sceKernelCheckCallback();
        SceCtrlData pad{}; sceCtrlPeekBufferPositive(0,&pad,1);
        uint32_t pressed=pad.buttons&~previous; previous=pad.buttons;
        const bool was_ime_active=ime_active;
        poll_ime();
        if(power_event_seen) notice="Событие питания: микрофон остановлен.";
        if(!ime_active && !was_ime_active && !power_event_seen) {
            int old=int(model.screen);
            if(pressed&SCE_CTRL_LTRIGGER) model.navigate(-1);
            if(pressed&SCE_CTRL_RTRIGGER) model.navigate(1);
            SceTouchData touch{}; sceTouchPeek(SCE_TOUCH_PORT_FRONT,&touch,1);
            if(touch.reportNum && !previous_touch) {
                int x=touch.report[0].x/2, y=touch.report[0].y/2;
                for(int i=0;i<cv::screen_count;++i) if(cv::inside(cv::tab_rect(i),x,y)) model.select(i);
            }
            previous_touch=touch.reportNum!=0;
            if(old!=int(model.screen)) {mic.stop(); notice.clear();}
            uint64_t now=sceKernelGetProcessTimeWide();
            if(now>=next_scroll) {
                if(pad.buttons&SCE_CTRL_UP) {model.scroll_by(-29,max_scroll); next_scroll=now+110000;}
                if(pad.buttons&SCE_CTRL_DOWN) {model.scroll_by(29,max_scroll); next_scroll=now+110000;}
            }
            if(pressed&SCE_CTRL_CROSS) {
                if(model.screen==cv::Screen::Chat) begin_ime();
                if(model.screen==cv::Screen::Voice) {if(mic.active()) mic.stop(); else if(power_callback_ready) mic.start(); else notice="Нет системного callback: микрофон отключён.";}
            }
            if(pressed&SCE_CTRL_SELECT) {model.draft.clear(); mic.stop(); notice="Локальные черновик и запись очищены.";}
            if(pressed&SCE_CTRL_START) running=false;
            mic.tick();
        }
        draw_screen();
    }
    mic.stop();
    if(power_callback_ready) scePowerUnregisterCallback(power_cb);
    if(power_cb>=0) sceKernelDeleteCallback(power_cb);
    if(ime_active) {sceImeDialogAbort(); sceImeDialogTerm();}
    vita2d_wait_rendering_done(); vita2d_free_pgf(font); vita2d_fini();
    sceAppUtilShutdown(); sceKernelExitProcess(0); return 0;
}
