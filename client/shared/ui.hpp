#pragma once
#include "session.hpp"
#include "diff.hpp"
#include "../src/ui_model.hpp"
#include <functional>

namespace cv {
enum class Page { Projects, Chat, Files, Approvals, Voice, Settings };
enum class Input { None, Draft, Endpoint, Pin, Search };
enum class Command { Project, Thread, NewThread, More, Edit, Send, Stop, Refresh, Allow, Decline, Endpoint, Pair, Disconnect, Mic, File, FileBack, PrevFile, NextFile, Search, ClearSearch, NextMatch };
struct Text {int x,y,size;unsigned color;std::string value;};
struct Button {Rect rect;std::string title;Command command;size_t index=0;bool enabled=true,hold=false;unsigned epoch=0;Page source=Page::Settings;std::string ticket;};
struct Scene {std::vector<Text> text;std::vector<Button> buttons;std::vector<std::pair<Rect,unsigned>> panels;};
constexpr unsigned Background=0x080c12,Panel=0x111923,Accent=0x16baf5,Foreground=0xedf3f9,Muted=0x9cadbf,Warning=0xf6c05f,Positive=0x62d99b,Negative=0xff9090;
using Measure=std::function<float(const std::string&,int)>;

class Ui {
    std::string cached_document;
    std::vector<std::string> cached_lines;
    Page cached_page=Page::Projects;
    unsigned epoch=0;
    std::string diff_source,diff_scope,approval_details;
    bool diff_upstream_truncated=false;
    std::vector<DiffRow> file_rows;
    std::vector<bool> file_hits;
    size_t rendered_file=DiffIndex::MaxFiles;
    int match_cursor=-1,match_scroll=-1;
    std::vector<size_t> filtered_files;
    void invalidate(){++epoch;match_cursor=match_scroll=-1;focus=scroll=max_scroll=0;hold.select_accept(false);}
    void sync_diff(const Session& s){
        const auto scope=s.project+"\n"+s.thread;
        const auto& source=s.view.at("diff").scalar;
        const bool limited=s.view.at("diffTruncated").yes();
        if(scope!=diff_scope){diff_scope=scope;file_open=false;file_selected=0;query.clear();list_selected=0;invalidate();}
        if(source!=diff_source||limited!=diff_upstream_truncated){
            std::string previous=file_selected<diff.files.size()?diff.files[file_selected].name:"";
            diff_source=source;diff_upstream_truncated=limited;diff.parse(source,limited);
            file_selected=0;for(size_t i=0;i<diff.files.size();++i)if(diff.files[i].name==previous){file_selected=i;break;}
            rendered_file=DiffIndex::MaxFiles;file_rows.clear();filtered_files=diff.matching(query);
            if(diff.files.empty())file_open=false;
            invalidate();
        }
        filtered_files=diff.matching(query);
        if(filtered_files.empty())file_open=false;
        if(file_open&&std::find(filtered_files.begin(),filtered_files.end(),file_selected)==filtered_files.end())file_selected=filtered_files.front();
    }
    void select_file(size_t i){if(i>=diff.files.size())return;file_selected=i;file_open=true;rendered_file=DiffIndex::MaxFiles;invalidate();}
    void step_file(int direction){
        auto it=std::find(filtered_files.begin(),filtered_files.end(),file_selected);
        if(it==filtered_files.end()||filtered_files.empty())return;
        auto index=int(it-filtered_files.begin());index=std::clamp(index+direction,0,int(filtered_files.size())-1);
        select_file(filtered_files[size_t(index)]);
    }
    static std::string fit(const std::string& value,int pixels,int size,const Measure& measure){
        if(measure(value,size)<=pixels)return value;
        size_t low=0,high=value.size();
        while(low<high){size_t mid=low+(high-low+1)/2,end=mid;while(end&&(static_cast<unsigned char>(value[end])&0xc0)==0x80)--end;
            if(measure(value.substr(0,end)+"...",size)<=pixels)low=mid;else high=mid-1;}
        while(low<value.size()&&low&&(static_cast<unsigned char>(value[low])&0xc0)==0x80)--low;
        return value.substr(0,low)+"...";
    }
public:
    Page page=Page::Settings;
    DiffIndex diff;
    size_t file_selected=0;
    bool file_open=false;
    std::string query;
    bool is_list()const{return page==Page::Projects||(page==Page::Files&&!file_open);}
    void vertical(const Session& s,int direction){
        hold.select_accept(false);
        if(is_list()){
            const auto n=page==Page::Files?filtered_files.size():(threads_mode?s.threads.size():s.projects.size());
            if(n){list_selected=std::clamp(list_selected+direction,0,int(n)-1);focus=list_selected%5;}
        }else scroll=std::clamp(scroll+direction*28,0,max_scroll);
    }
    void back(){
        if(page==Page::Files&&file_open){file_open=false;invalidate();}
        else if(page==Page::Projects){threads_mode=false;list_selected=0;invalidate();}
        else jump(Page::Projects);
    }
    void focus_by(int direction,size_t count){if(count){focus=(focus+int(count)+direction)%int(count);hold.select_accept(false);}}
    std::string initial_text(const Session& s,Input kind)const{return kind==Input::Draft?s.draft:kind==Input::Endpoint?s.endpoint:kind==Input::Search?query:"";}
    int focus=0,scroll=0,max_scroll=0,list_selected=0;
    bool threads_mode=false;
    ApprovalHold hold;
    std::string approval_ticket;
    bool mic_requested=false;
    void tab(int delta){jump(static_cast<Page>((int(page)+delta+6)%6));}
    void jump(Page p){page=p;list_selected=0;invalidate();mic_requested=false;}
    static std::string shorten(const std::string& s,size_t count=55){
        if(s.size()<=count)return s;
        size_t end=count;while(end&&(static_cast<unsigned char>(s[end])&0xc0)==0x80)--end;
        return s.substr(0,end)+"...";
    }
    Scene draw(Session& s,Measure measure) {
        Scene out;
        if(page==Page::Files)sync_diff(s);
        if(page==Page::Approvals){
            const auto& approvals=s.view.at("approvals").array;
            const auto ticket=approvals.empty()?std::string():approvals[0].at("id").str();
            const auto details=approvals.empty()?std::string():approvals[0].at("details").str();
            if(ticket!=approval_ticket||details!=approval_details){approval_ticket=ticket;approval_details=details;invalidate();}
        }
        auto text=[&](int x,int y,const std::string& v,unsigned c=Foreground,int size=20){out.text.push_back({x,y,size,c,v});};
        auto button=[&](Rect r,std::string title,Command c,bool enabled=true,size_t index=0,bool held=false){out.buttons.push_back({r,std::move(title),c,index,enabled,held,epoch,page,approval_ticket});};
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
            list_selected=list.empty()?0:std::clamp(list_selected,0,int(list.size())-1);
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
            if(!file_open){
                text(32,142,"Изменённые файлы: "+std::to_string(filtered_files.size()),Foreground,23);
                text(32,169,query.empty()?"Только просмотр. Стрелки — выбор, X — открыть.":"Поиск (точное совпадение): "+query,Muted,18);
                list_selected=filtered_files.empty()?0:std::clamp(list_selected,0,int(filtered_files.size())-1);
                const size_t first=size_t(list_selected/5)*5;
                for(size_t i=first;i<filtered_files.size()&&i<first+5;++i){const auto index=filtered_files[i];const auto& f=diff.files[index];
                    std::string stats=f.binary?" [binary]":" [+"+std::to_string(f.added)+" -"+std::to_string(f.removed)+"]";
                    if(f.partial)stats+=" [частично]";
                    button({32,182+int(i-first)*52,896,46},fit(f.name,650,18,measure)+stats,Command::File,true,index);
                }
                if(filtered_files.empty())text(32,228,diff.files.empty()?"Изменений пока нет.":"Совпадений нет. Очистите поиск.",Muted,20);
                if(diff.truncated)text(32,460,"Получена только часть diff. Полная версия — на компьютере.",Warning,16);
                button({24,480,280,38},"Найти в diff",Command::Search,!diff.files.empty());
                button({322,480,280,38},"Очистить поиск",Command::ClearSearch,!query.empty());
                button({620,480,314,38},"Обновить",Command::Refresh,s.ready);
                max_scroll=scroll=0;
            }else{
                const auto& file=diff.files[file_selected];
                text(32,140,file.name,Foreground,22);
                text(32,168,(file.binary?std::string("Двоичный файл; исходные данные не открываются."):"Видимые строки: +"+std::to_string(file.added)+" / -"+std::to_string(file.removed))+
                    ((file.partial||diff.truncated)?"  / НЕПОЛНЫЙ DIFF":""),file.partial||diff.truncated?Warning:Muted,17);
                if(rendered_file!=file_selected){file_rows.clear();file_hits.clear();for(const auto& row:file.rows){
                    auto lines=wrap(row.text,878.0f,[&](const std::string& line){return measure(line,20);});
                    for(auto& line:lines){file_rows.push_back({std::move(line),row.kind});file_hits.push_back(!query.empty()&&row.text.find(query)!=std::string::npos);}
                }rendered_file=file_selected;}
                max_scroll=std::max(0,int(file_rows.size())*28-252);scroll=std::clamp(scroll,0,max_scroll);
                int y=203-scroll;
                size_t row_index=0;
                for(const auto& row:file_rows){if(y>=203&&y<=427){
                    unsigned c=row.kind==DiffKind::Add?Positive:row.kind==DiffKind::Remove?Negative:row.kind==DiffKind::Hunk?Accent:Foreground;
                    if(file_hits[row_index])out.panels.push_back({{30,y-21,896,27},0x35435a});
                    text(32,y,row.text,c,20);
                }y+=28;++row_index;}
                text(32,459,query.empty()?"Только чтение. Назад — список; стрелки — прокрутка.":"Совпадения подсвечены: "+query,Muted,16);
                button({24,480,174,38},"Список",Command::FileBack);
                const auto it=std::find(filtered_files.begin(),filtered_files.end(),file_selected);
                button({208,480,174,38},"Пред. файл",Command::PrevFile,it!=filtered_files.begin());
                button({392,480,174,38},"След. файл",Command::NextFile,it!=filtered_files.end()&&it+1!=filtered_files.end());
                button({576,480,174,38},"Поиск",Command::Search);
                button({760,480,174,38},"Совпадение",Command::NextMatch,!query.empty());
            }
        } else if(page==Page::Approvals){
            const auto& approvals=s.view.at("approvals").array;
            const auto ticket=approvals.empty()?std::string():approvals[0].at("id").str();
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
        // Fit using the actual renderer metrics, not UTF-8 byte counts.
        for(auto& t:out.text)t.value=fit(t.value,std::max(20,944-t.x),t.size,measure);
        for(auto& b:out.buttons)b.title=fit(b.title,b.rect.w-24,18,measure);
        return out;
    }
    Input activate(Session& s,const Button& b,bool hold_complete=false){
        if(b.epoch!=epoch||b.source!=page||!b.enabled||(b.hold&&!hold_complete))return Input::None;
        if(b.command==Command::Allow||b.command==Command::Decline){
            const auto& a=s.view.at("approvals").array;
            if(a.empty()||b.ticket!=a[0].at("id").str()||approval_details!=a[0].at("details").str()||s.stale)return Input::None;
            if(b.command==Command::Allow&&scroll<max_scroll)return Input::None;
        }
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
        case Command::File:select_file(b.index);break;
        case Command::FileBack:back();break;
        case Command::PrevFile:step_file(-1);break;
        case Command::NextFile:step_file(1);break;
        case Command::Search:return Input::Search;
        case Command::ClearSearch:query.clear();list_selected=0;rendered_file=DiffIndex::MaxFiles;invalidate();break;
        case Command::NextMatch:{
            const int after=scroll==match_scroll?match_cursor:scroll/28-1;
            int chosen=-1;
            for(size_t i=0;i<file_rows.size();++i)if(int(i)>after&&file_hits[i]){chosen=int(i);break;}
            if(chosen<0)for(size_t i=0;i<file_rows.size();++i)if(file_hits[i]){chosen=int(i);break;}
            if(chosen>=0){match_cursor=chosen;scroll=std::min(chosen*28,max_scroll);match_scroll=scroll;}
            else s.notice="Совпадение в имени файла; в строках не найдено";
            hold.select_accept(false);break;
        }
        }
        return Input::None;
    }
    Input tap(Session& s,const Scene& scene,int x,int y){
        for(int i=0;i<6;++i)if(inside({16+156*i,58,148,40},x,y)){jump(static_cast<Page>(i));return Input::None;}
        for(size_t i=0;i<scene.buttons.size();++i)if(inside(scene.buttons[i].rect,x,y)){
            if(focus!=int(i))hold.select_accept(false);
            focus=int(i);return activate(s,scene.buttons[i]);
        }
        return Input::None;
    }
    void apply_text(Session& s,Input kind,const std::string& text){
        if(kind==Input::Draft){s.draft=text;s.notice="Черновик изменён. Отправка — отдельной кнопкой.";}
        else if(kind==Input::Endpoint){if(s.ready||s.has("pair")||s.has("status"))return; if(valid_endpoint(text)){s.endpoint=text;s.notice="Адрес задан";}else s.notice="Формат: https://192.168.1.10:8765";}
        else if(kind==Input::Pin)s.pair(text);
        else if(kind==Input::Search){
            if(text.size()>128||!valid_utf8(text)||std::any_of(text.begin(),text.end(),[](unsigned char c){return c<32||c==127;})){s.notice="Поиск: до 128 байт UTF-8, одна строка";return;}
            query=text;list_selected=0;rendered_file=DiffIndex::MaxFiles;invalidate();s.notice="Поиск только в полученном diff, с учётом регистра";
        }
        scroll=0;
    }
};
} // namespace cv
