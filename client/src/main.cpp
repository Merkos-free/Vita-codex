// Native connected-client candidate. Hardware and account validation remain open.
#include "../shared/ui.hpp"
#include "microphone.hpp"
#include "ime_text.hpp"
#include <vita2d.h>
#include <psp2/apputil.h>
#include <psp2/common_dialog.h>
#include <psp2/ctrl.h>
#include <psp2/display.h>
#include <psp2/ime_dialog.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/threadmgr/callback.h>
#include <psp2/net/net.h>
#include <psp2/net/netctl.h>
#include <psp2/power.h>
#include <psp2/sysmodule.h>
#include <psp2/touch.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>

namespace {
cv::Session* session=nullptr;
cv::Ui ui;
MicrophoneProbe mic;
vita2d_pgf* font=nullptr;
bool suspended=false;
int power_event(int,int,int flags,void*) {
    mic.stop();ui.mic_requested=false;
    if(flags&(SCE_POWER_CB_SYSTEM_SUSPEND|SCE_POWER_CB_SYSTEM_RESUMING|SCE_POWER_CB_SYSTEM_RESUME|SCE_POWER_CB_APP_RESUME))suspended=true;
    return 0;
}
unsigned rgba(unsigned c){return RGBA8((c>>16)&255,(c>>8)&255,c&255,255);}
void box(cv::Rect r,unsigned c,int radius=8){
    auto color=rgba(c);
    vita2d_draw_rectangle(r.x+radius,r.y,r.w-radius*2,r.h,color);
    vita2d_draw_rectangle(r.x,r.y+radius,r.w,r.h-radius*2,color);
    for(int x:{r.x+radius,r.x+r.w-radius})for(int y:{r.y+radius,r.y+r.h-radius})vita2d_draw_fill_circle(x,y,radius,color);
}
cv::Input input=cv::Input::None;
uint16_t ime_buffer[SCE_IME_DIALOG_MAX_TEXT_LENGTH+1]{};
std::vector<uint16_t> initial,title;
void begin_input(cv::Input kind){
    if(kind==cv::Input::None||input!=cv::Input::None)return;
    const std::string value=ui.initial_text(*session,kind);
    title=cv::to_ime(kind==cv::Input::Draft?"Задание для Codex":kind==cv::Input::Endpoint?"HTTPS-адрес компьютера":kind==cv::Input::Search?"Поиск в изменениях":"Одноразовый код с компьютера",SCE_IME_DIALOG_MAX_TITLE_LENGTH);
    initial=cv::to_ime(value,SCE_IME_DIALOG_MAX_TEXT_LENGTH);
    std::memset(ime_buffer,0,sizeof ime_buffer);
    SceImeDialogParam p;sceImeDialogParamInit(&p);
    p.supportedLanguages=SCE_IME_LANGUAGE_ENGLISH|SCE_IME_LANGUAGE_RUSSIAN;
    p.languagesForced=SCE_FALSE;p.type=SCE_IME_DIALOG_TEXTBOX_MODE_DEFAULT;
    p.textBoxMode=SCE_IME_DIALOG_TEXTBOX_MODE_DEFAULT;p.dialogMode=SCE_IME_DIALOG_DIALOG_MODE_WITH_CANCEL;
    p.title=title.data();p.initialText=initial.data();p.maxTextLength=kind==cv::Input::Pin?6:kind==cv::Input::Search?128:SCE_IME_DIALOG_MAX_TEXT_LENGTH;p.inputTextBuffer=ime_buffer;
    if(sceImeDialogInit(&p)<0)session->notice="Не удалось открыть клавиатуру";else input=kind;
}
void poll_input(){
    if(input==cv::Input::None||sceImeDialogGetStatus()!=SCE_COMMON_DIALOG_STATUS_FINISHED)return;
    SceImeDialogResult r{};
    if(sceImeDialogGetResult(&r)>=0&&r.result>=0&&r.button==SCE_IME_DIALOG_BUTTON_ENTER)ui.apply_text(*session,input,cv::utf16_to_utf8(ime_buffer,SCE_IME_DIALOG_MAX_TEXT_LENGTH));
    sceImeDialogTerm();input=cv::Input::None;
    std::memset(ime_buffer,0,sizeof ime_buffer);std::fill(initial.begin(),initial.end(),0);initial.clear();
}
void load_connection(){
    session->ca_file="ux0:data/vita-codex/ca.pem";
    FILE* f=std::fopen("ux0:data/vita-codex/connection.json","rb");if(!f)return;
    char data[1025];size_t n=std::fread(data,1,sizeof data,f);std::fclose(f);
    try{if(n>1024)throw std::runtime_error("size");auto j=cv::parse_json(std::string(data,n));auto e=j.at("endpoint").str();if(cv::valid_endpoint(e))session->endpoint=e;}
    catch(...){session->notice="Некорректный connection.json; введите адрес вручную";}
}
struct Network {
    void* memory=nullptr;bool initialized=false,control=false,loaded=false;
    Network(){
        loaded=sceSysmoduleLoadModule(SCE_SYSMODULE_NET)>=0;if(!loaded)return;
        memory=std::calloc(1,2*1024*1024);if(!memory)return;
        SceNetInitParam p{};p.memory=memory;p.size=2*1024*1024;p.flags=0;
        initialized=sceNetInit(&p)>=0;if(initialized)control=sceNetCtlInit()>=0;
    }
    ~Network(){if(control)sceNetCtlTerm();if(initialized)sceNetTerm();std::free(memory);if(loaded)sceSysmoduleUnloadModule(SCE_SYSMODULE_NET);}
};
}
int main(){
    SceAppUtilInitParam init{};SceAppUtilBootParam boot{};
    if(sceAppUtilInit(&init,&boot)<0)return 1;
    if(vita2d_init()<0){sceAppUtilShutdown();return 2;}
    font=vita2d_load_default_pgf();if(!font){vita2d_fini();sceAppUtilShutdown();return 3;}
    vita2d_set_clear_color(rgba(cv::Background));
    sceCtrlSetSamplingMode(SCE_CTRL_MODE_ANALOG);sceTouchSetSamplingState(SCE_TOUCH_PORT_FRONT,SCE_TOUCH_SAMPLING_STATE_START);
    auto cb=sceKernelCreateCallback("codex-vita-power",0,power_event,nullptr);
    bool callback_ready=cb>=0&&scePowerRegisterCallback(cb)>=0;
    try{
        Network network;
        cv::Session connection;session=&connection;load_connection();
        if(!network.control)connection.notice="Сеть не инициализирована. Интерфейс доступен офлайн.";
        uint32_t previous=0;bool touch_before=false,running=true;
        uint64_t last=sceKernelGetProcessTimeWide(),next_poll=0,next_repeat=0;
        while(running){
            sceKernelCheckCallback();uint64_t now=sceKernelGetProcessTimeWide();
            if(suspended||now-last>2000000){connection.suspend();mic.stop();ui.mic_requested=false;suspended=false;}
            unsigned elapsed=unsigned(std::min<uint64_t>((now-last)/1000,100));last=now;
            connection.poll();poll_input();
            if(connection.ready&&now>=next_poll&&input==cv::Input::None){connection.refresh();next_poll=now+750000;}
            auto scene=ui.draw(connection,[](const std::string& text,int size){return vita2d_pgf_text_width(font,float(size)/20.0f,text.c_str());});
            SceCtrlData pad{};sceCtrlPeekBufferPositive(0,&pad,1);auto pressed=pad.buttons&~previous;previous=pad.buttons;
            if(input==cv::Input::None){
                if(pressed&SCE_CTRL_START)running=false;
                if(pressed&SCE_CTRL_LTRIGGER){ui.tab(-1);mic.stop();}
                if(pressed&SCE_CTRL_RTRIGGER){ui.tab(1);mic.stop();}
                if(pressed&SCE_CTRL_CIRCLE){ui.back();mic.stop();}
                if(pressed&SCE_CTRL_SELECT){if(!connection.uncertain.empty())connection.reconcile();connection.refresh();}
                if(now>=next_repeat&&(pad.buttons&(SCE_CTRL_UP|SCE_CTRL_DOWN))){
                    int dir=(pad.buttons&SCE_CTRL_DOWN)?1:-1;
                    ui.vertical(connection,dir);
                    next_repeat=now+110000;ui.hold.select_accept(false);
                }
                scene=ui.draw(connection,[](const std::string& text,int size){return vita2d_pgf_text_width(font,float(size)/20.0f,text.c_str());});
                if(!scene.buttons.empty()){
                    if(pressed&SCE_CTRL_LEFT)ui.focus_by(-1,scene.buttons.size());
                    if(pressed&SCE_CTRL_RIGHT)ui.focus_by(1,scene.buttons.size());
                    ui.focus=std::clamp(ui.focus,0,int(scene.buttons.size())-1);
                    const auto& b=scene.buttons[size_t(ui.focus)];
                    if(pressed&SCE_CTRL_CROSS)begin_input(ui.activate(connection,b));
                    if(b.hold&&b.enabled){if(!ui.hold.accept_selected)ui.hold.select_accept(true);if(ui.hold.update(pad.buttons&SCE_CTRL_CROSS,elapsed))ui.activate(connection,b,true);}
                    else ui.hold.select_accept(false);
                }
                SceTouchData touch{};sceTouchPeek(SCE_TOUCH_PORT_FRONT,&touch,1);
                if(touch.reportNum&&!touch_before){
                    scene=ui.draw(connection,[](const std::string& text,int size){return vita2d_pgf_text_width(font,float(size)/20.0f,text.c_str());});
                    begin_input(ui.tap(connection,scene,touch.report[0].x/2,touch.report[0].y/2));
                }
                touch_before=touch.reportNum!=0;
                if(ui.mic_requested&&!mic.active()){if(callback_ready){mic.start();}else{connection.notice="Микрофон отключён: power callback недоступен";ui.mic_requested=false;}}
                if(!ui.mic_requested)mic.stop();
                mic.tick();if(ui.mic_requested&&!mic.active())ui.mic_requested=false;
            }
            scene=ui.draw(connection,[](const std::string& text,int size){return vita2d_pgf_text_width(font,float(size)/20.0f,text.c_str());});
            vita2d_start_drawing();vita2d_clear_screen();
            for(const auto& p:scene.panels){if(p.first.w<16)vita2d_draw_rectangle(p.first.x,p.first.y,p.first.w,p.first.h,rgba(p.second));else box(p.first,p.second);}
            for(size_t i=0;i<scene.buttons.size();++i){const auto& b=scene.buttons[i];box(b.rect,b.enabled?(int(i)==ui.focus?cv::Accent:0x243447):0x1b232c);vita2d_pgf_draw_text(font,b.rect.x+12,b.rect.y+26,rgba(b.enabled&&int(i)==ui.focus?cv::Background:cv::Muted),0.9f,b.title.c_str());}
            for(const auto& t:scene.text)vita2d_pgf_draw_text(font,t.x,t.y,rgba(t.color),float(t.size)/20.0f,t.value.c_str());
            if(ui.page==cv::Page::Voice&&mic.active())vita2d_draw_rectangle(32,448,int(880*mic.level()),7,rgba(cv::Accent));
            if(ui.hold.held_ms)vita2d_draw_rectangle(304,514,int(340*ui.hold.held_ms/1500),4,rgba(cv::Positive));
            vita2d_end_drawing();if(input!=cv::Input::None)vita2d_common_dialog_update();vita2d_swap_buffers();sceDisplayWaitVblankStart();
        }
        connection.disconnect();session=nullptr;
    }catch(...){session=nullptr;}
    mic.stop();if(input!=cv::Input::None)sceImeDialogTerm();
    if(callback_ready)scePowerUnregisterCallback(cb);
    if(cb>=0)sceKernelDeleteCallback(cb);
    vita2d_wait_rendering_done();vita2d_free_pgf(font);vita2d_fini();sceAppUtilShutdown();sceKernelExitProcess(0);return 0;
}
