#pragma once
#include "session.hpp"
#include "../src/ui_model.hpp"
#include <functional>

namespace cv {
enum class Page { Projects, Chat, Files, Approvals, Voice, Settings };
enum class Input { None, Draft, Endpoint, Pin };
enum class Command { Project, Thread, NewThread, More, Edit, Send, Stop, Refresh, Allow, Decline, Endpoint, Pair, Disconnect, Mic };
struct Text {int x,y,size;unsigned color;std::string value;};
struct Button {Rect rect;std::string title;Command command;size_t index=0;bool enabled=true,hold=false;};
struct Scene {std::vector<Text> text;std::vector<Button> buttons;std::vector<std::pair<Rect,unsigned>> panels;};
constexpr unsigned Background=0x080c12,Panel=0x111923,Accent=0x16baf5,Foreground=0xedf3f9,Muted=0x9cadbf,Warning=0xf6c05f,Positive=0x62d99b,Negative=0xff9090;
using Measure=std::function<float(const std::string&,int)>;

class Ui {
    std::string cached_document;
    std::vector<std::string> cached_lines;
    Page cached_page=Page::Projects;
public:
    Page page=Page::Settings;
    int focus=0,scroll=0,max_scroll=0,list_selected=0;
    bool threads_mode=false;
    ApprovalHold hold;
    std::string approval_ticket;
    bool mic_requested=false;
    void tab(int delta){page=static_cast<Page>((int(page)+delta+6)%6);focus=scroll=0;hold.select_accept(false);mic_requested=false;}
    void jump(Page p){page=p;focus=scroll=0;hold.select_accept(false);mic_requested=false;}
    static std::string shorten(const std::string& s,size_t count=55){
        if(s.size()<=count)return s;
        size_t end=count;while(end&&(static_cast<unsigned char>(s[end])&0xc0)==0x80)--end;
        return s.substr(0,end)+"...";
    }
    Scene draw(Session& s,Measure measure) {
        Scene out;
        auto text=[&](int x,int y,const std::string& v,unsigned c=Foreground,int size=20){out.text.push_back({x,y,size,c,v});};
        auto button=[&](Rect r,std::string title,Command c,bool enabled=true,size_t index=0,bool held=false){out.buttons.push_back({r,std::move(title),c,index,enabled,held});};
        out.panels.push_back({{16,110,928,358},Panel});
        text(24,37,"< > CODEX VITA",Foreground,25);
        text(570,35,s.ready?(s.stale?"СВЯЗЬ / ОБНОВЛЕНИЕ":"ПОДКЛЮЧЕНО"):"НЕ ПОДКЛЮЧЕНО",s.ready&&!s.stale?Positive:Warning,18);
        const char* tabs[]={"Проекты","Чат","Файлы","Запросы","Голос","Настройки"};
        for(int i=0;i<6;++i){out.panels.push_back({{16+156*i,58,148,40},int(page)==i?Accent:Panel});text(28+156*i,85,tabs[i],int(page)==i?Background:Foreground,19);}
        std::string doc;
        if(page==Page::Projects){
            text(32,145,threads_mode?"Диалоги: "+shorten(s.project):"Разрешённые проекты",Foreground,23);
            const auto& list=threads_mode?s.threads:s.projects;
            if(list.empty())text(32,207,s.ready?"Список пуст. Создайте диалог или выберите папку на ПК.":"Сначала подключите компьютер в настройках.",Muted,18);
            size_t first=size_t(std::max(0,list_selected)/5)*5;
            for(size_t i=first;i<list.size()&&i<first+5;++i){
                button({32,166+int(i-first)*52,896,46},shorten(list[i].at("name").str(list[i].at("id").str()),80),threads_mode?Command::Thread:Command::Project,s.ready&&!s.busy(),i);
            }
            if(threads_mode){button({24,480,240,38},"Новый диалог",Command::NewThread,s.ready&&!s.busy());button({282,480,240,38},"Следующая страница",Command::More,!s.next_cursor.empty());}
        } else if(page==Page::Chat){
            doc="Диалог: "+s.thread+"\n";
            for(const auto& m:s.view.at("messages").array)doc+="\n"+(m.at("role").str()=="user"?std::string("ВЫ"):std::string("CODEX"))+"\n"+m.at("text").str()+"\n";
            if(s.view.at("messages").array.empty())doc+="\nОткройте или создайте диалог во вкладке «Проекты».\n";
            if(s.view.at("historyTruncated").yes())doc+="\n[Показан только конец длинной истории]\n";
            if(!s.view.at("tools").array.empty()){doc+="\nДЕЙСТВИЯ\n";for(const auto& tool:s.view.at("tools").array)doc+=shorten(tool.at("command").str(tool.at("type").str()),160)+" / "+tool.at("status").str()+"\n";}
            doc+="\nЧЕРНОВИК\n"+(s.draft.empty()?std::string("Нажмите «Написать»."):s.draft);
            button({24,480,210,38},"Написать",Command::Edit);
            button({250,480,210,38},"Отправить",Command::Send,s.can_send()&&!s.draft.empty());
            button({476,480,210,38},"Остановить",Command::Stop,s.ready&&!s.thread.empty());
            button({702,480,232,38},"Обновить",Command::Refresh,s.ready);
        } else if(page==Page::Files){
            doc="Изменения / "+s.project+"\n\n"+s.view.at("diff").str("Пока нет полученных изменений.");
            if(s.view.at("diffTruncated").yes())doc+="\n[Diff ограничен размером; полная версия на компьютере]";
            button({24,480,260,38},"Обновить",Command::Refresh,s.ready);
        } else if(page==Page::Approvals){
            const auto& approvals=s.view.at("approvals").array;
            const auto ticket=approvals.empty()?std::string():approvals[0].at("id").str();
            if(ticket!=approval_ticket){approval_ticket=ticket;scroll=focus=0;hold.select_accept(false);}
            if(approvals.empty())doc="Запросов подтверждения нет.\n\nРазрешения рабочего пространства задаются на компьютере. Не каждое действие Codex требует отдельного подтверждения.";
            else doc="Запрос доступа / "+s.project+"\nПросмотрите ВСЕ детали. Удерживайте X на «Разрешить».\n\n"+approvals[0].at("details").str();
            button({24,480,260,38},"Отклонить",Command::Decline,s.ready&&!s.stale&&!ticket.empty());
            button({304,480,340,38},"Разрешить: держать X",Command::Allow,s.ready&&!s.stale&&!ticket.empty()&&scroll>=max_scroll,0,true);
            button({664,480,270,38},"Обновить",Command::Refresh,s.ready);
        } else if(page==Page::Voice){
            doc="Встроенная диктовка Codex\n\nПока не подключена. Платного Speech-to-Text API нет.\n\nКнопка ниже запускает только локальный индикатор микрофона Vita. Звук не сохраняется и не отправляется на компьютер.\n\nАппаратный тест и штатная диктовка — отдельные этапы.";
            button({24,480,330,38},mic_requested?"Остановить индикатор":"Проверить микрофон",Command::Mic);
        } else {
            doc="Подключение к вашему компьютеру\n\nАдрес: "+(s.endpoint.empty()?std::string("не задан"):s.endpoint)+"\n\nCA-файл: "+s.ca_file+"\n\n1. Подготовьте локальный Bridge на компьютере.\n2. Перенесите его публичный сертификат на Vita.\n3. Введите HTTPS-адрес, затем код с компьютера.\n\nЛогин OpenAI остаётся на ПК. Токен Vita — только в памяти. Никаких паролей или ключей OpenAI вводить здесь не нужно.";
            button({24,480,280,38},"Адрес компьютера",Command::Endpoint,!s.ready&&!s.has("pair")&&!s.has("status"));
            button({322,480,280,38},"Ввести код",Command::Pair,!s.ready&&!s.has("pair"));
            button({620,480,314,38},"Отключить",Command::Disconnect,s.ready);
        }
        if(!doc.empty()) {
            if(doc!=cached_document||cached_page!=page){cached_document=doc;cached_page=page;cached_lines=wrap(doc,880.0f,[&](const std::string& line){return measure(line,20);});}
            max_scroll=std::max(0,int(cached_lines.size())*28-300);scroll=std::clamp(scroll,0,max_scroll);
            int y=145-scroll;
            for(const auto& line:cached_lines){if(y>=138&&y<=449){unsigned c=Foreground;if(line=="ВЫ"||line=="CODEX"||line=="ЧЕРНОВИК")c=Accent;if(page==Page::Files&&!line.empty()){if(line[0]=='+')c=Positive;else if(line[0]=='-')c=Negative;}text(32,y,line,c);}y+=28;}
            if(max_scroll>0){out.panels.push_back({{934,122,3,330},Muted});out.panels.push_back({{932,122+(scroll*280/std::max(1,max_scroll)),7,50},Accent});}
        }
        if(page==Page::Approvals)for(auto& b:out.buttons)if(b.command==Command::Allow)b.enabled=b.enabled&&scroll>=max_scroll;
        if(focus<0||focus>=int(out.buttons.size()))focus=0;
        const auto status=s.view.at("status").str();
        text(24,540,shorten(s.notice+(status.empty()?"":" / "+status),125),Muted,16);
        return out;
    }
    Input activate(Session& s,const Button& b,bool hold_complete=false){
        if(!b.enabled||(b.hold&&!hold_complete))return Input::None;
        switch(b.command){
        case Command::Project:if(s.choose_project(b.index)){threads_mode=true;focus=list_selected=0;}break;
        case Command::Thread:if(s.resume(b.index))jump(Page::Chat);break;
        case Command::NewThread:if(s.new_thread())jump(Page::Chat);break;
        case Command::More:if(s.more_threads())focus=list_selected=0;break;
        case Command::Edit:return Input::Draft;
        case Command::Endpoint:return Input::Endpoint;
        case Command::Pair:return Input::Pin;
        case Command::Send:s.send();break;
        case Command::Stop:s.interrupt();break;
        case Command::Refresh:if(!s.uncertain.empty())s.reconcile();s.refresh();break;
        case Command::Allow:s.decide(approval_ticket,true);hold.select_accept(false);break;
        case Command::Decline:s.decide(approval_ticket,false);break;
        case Command::Disconnect:s.disconnect();break;
        case Command::Mic:mic_requested=!mic_requested;break;
        }
        return Input::None;
    }
    void apply_text(Session& s,Input kind,const std::string& text){
        if(kind==Input::Draft){s.draft=text;s.notice="Черновик изменён. Отправка — отдельной кнопкой.";}
        else if(kind==Input::Endpoint){if(s.ready||s.has("pair")||s.has("status"))return; if(valid_endpoint(text)){s.endpoint=text;s.notice="Адрес задан";}else s.notice="Формат: https://192.168.1.10:8765";}
        else if(kind==Input::Pin)s.pair(text);
        scroll=0;
    }
};
} // namespace cv
