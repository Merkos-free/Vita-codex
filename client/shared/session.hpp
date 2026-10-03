#pragma once
#include "https.hpp"
#include "json.hpp"
#include <algorithm>
#include <map>
#include <set>

namespace cv {
class Session {
    struct Pending {std::string operation,project,thread,request_id;unsigned long long revision=0;};
    Https net;
    unsigned sequence=0;
    unsigned long long revision=0; // Discard snapshots captured before a state-changing request.
    std::string token;
    std::map<unsigned,Pending> pending;
    std::map<std::string,Pending> unresolved;
    void mark_uncertain(const Pending& p){if(!p.request_id.empty()){unresolved[p.request_id]=p;uncertain=unresolved.begin()->first;}}
    bool post(const std::string& op,const Json& data,bool mutation=false) {
        if(token.empty()||(!ready&&op!="status"))return false;
        if(has(op))return false;
        const unsigned id=++sequence;
        const std::string ticket="vita-"+std::to_string(id);
        auto body=Json::obj({{"operation",Json(op)},{"data",data}});
        if(mutation)body.object["requestId"]=Json(ticket);
        if(!net.start(id,endpoint,ca_file,"/v1/action",body.dump(),token)){notice="Не удалось начать запрос";return false;}
        if(mutation){++revision;stale=true;}
        pending[id]={op,project,thread,mutation?ticket:(op=="requestStatus"?data.at("requestId").str():""),revision};
        return true;
    }
    Json scope()const{return Json::obj({{"project",Json(project)},{"thread",Json(thread)}});}
    void consume(const Pending& p,const Json& value) {
        if(p.operation=="requestStatus") {
            auto it=unresolved.find(p.request_id);
            if(value.at("state").str()=="done" && value.at("status").scalar=="200" && it!=unresolved.end()){
                const auto original=it->second;unresolved.erase(it);
                uncertain=unresolved.empty()?"":unresolved.begin()->first;
                consume(original,value.at("response"));
                notice="Ответ восстановлен; запрос не повторялся";
            }else notice="Исход прежнего запроса не подтверждён. Автоповтор запрещён.";
        }else if(p.operation=="status") {
            if(value.at("protocolVersion").scalar!="2"||value.at("authMode").str()!="chatgpt"||value.at("codex").str()!="connected")throw std::runtime_error("Несовместимый bridge или нет входа ChatGPT");
            ready=true;notice="Соединение подтверждено";post("projects",Json::obj());
        } else if(p.operation=="projects") {
            if(value.at("projects").type!=Json::Type::Array||value.at("projects").array.size()>128)throw std::runtime_error("Некорректный список проектов");
            projects=value.at("projects").array;
        } else if(p.project!=project)return;
        else if(p.operation=="threads") {
            if(value.at("threads").type!=Json::Type::Array||value.at("threads").array.size()>30)throw std::runtime_error("Некорректный список диалогов");
            threads=value.at("threads").array;
            next_cursor=value.at("nextCursor").str();
        } else if(p.operation=="newThread"||p.operation=="resume") {
            const auto ident=value.at("threadId").str();
            if(ident.empty()||ident.size()>160)throw std::runtime_error("Некорректный ID диалога");
            ++revision;stale=true;thread=ident;view=Json::obj();refresh();
        } else if(p.thread!=thread)return;
        else if(p.operation=="snapshot") {
            if(value.at("threadId").str()!=thread)throw std::runtime_error("Ответ от другого диалога");
            if(p.revision!=revision){refresh();return;}
            view=value;stale=false;
        } else if(p.operation=="send"||p.operation=="approval"||p.operation=="interrupt") {
            ++revision;stale=true;
            notice=p.operation=="send"?"Задание принято; ожидается результат":"Запрос принят; ожидается состояние";
            refresh();
        }
    }
public:
    bool ready=false,stale=true;
    std::string endpoint,ca_file,project,thread,draft,notice="Компьютер не подключён",uncertain,next_cursor;
    std::vector<Json> projects,threads;
    Json view=Json::obj();
    ~Session(){disconnect();}
    bool has(const std::string& op)const {for(const auto& p:pending)if(p.second.operation==op)return true;return false;}
    bool busy()const {return has("send")||has("newThread")||has("resume")||has("approval")||has("interrupt");}
    bool can_send()const {
        const auto s=view.at("status").str();
        return ready&&!stale&&!thread.empty()&&uncertain.empty()&&!busy()&&
            (s=="idle"||s=="completed"||s=="interrupted"||s=="failed");
    }
    bool pair(const std::string& pin) {
        if(!pending.empty()||ready)return false;
        if(pin.size()!=6||!std::all_of(pin.begin(),pin.end(),[](char c){return c>='0'&&c<='9';})){notice="Нужен шестизначный код";return false;}
        const unsigned id=++sequence;
        if(!net.start(id,endpoint,ca_file,"/v1/pair",Json::obj({{"pin",Json(pin)}}).dump())){notice="Нужен HTTPS IPv4:порт и доверенный сертификат";return false;}
        pending[id]={"pair","","",""};notice="Проверка сертификата и кода...";return true;
    }
    void poll() {
        for(auto& r:net.poll()) {
            auto it=pending.find(r.id);if(it==pending.end())continue;
            const auto p=it->second;pending.erase(it);
            try {
                if(!r.ok())throw std::runtime_error(r.error.empty()?"Ошибка bridge HTTP "+std::to_string(r.status):r.error);
                auto v=parse_json(r.body);
                if(v.type!=Json::Type::Object)throw std::runtime_error("Ответ должен быть JSON объектом");
                if(p.operation=="pair") {
                    auto t=v.at("token").str();
                    if(v.at("protocolVersion").scalar!="2"||t.size()<32||t.size()>128||!std::all_of(t.begin(),t.end(),[](unsigned char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-';}))throw std::runtime_error("Некорректное сопряжение");
                    token=t;post("status",Json::obj());
                } else consume(p,v);
            } catch(const std::exception& e) {
                notice=e.what();stale=true;
                if(p.operation!="requestStatus")mark_uncertain(p);
                if(r.status==401){disconnect();notice="Подключение отозвано. Нужен новый код на ПК.";}
            }
        }
    }
    bool choose_project(size_t i) {
        if(!ready||busy()||has("threads")||!uncertain.empty()||i>=projects.size())return false;
        const auto id=projects[i].at("id").str();if(id.empty()||id.size()>80)return false;
        ++revision;project=id;thread.clear();threads.clear();next_cursor.clear();view=Json::obj();stale=true;
        return post("threads",Json::obj({{"project",Json(project)}}));
    }
    bool more_threads() {
        if(next_cursor.empty()||busy())return false;
        return post("threads",Json::obj({{"project",Json(project)},{"cursor",Json(next_cursor)}}));
    }
    bool new_thread(){return ready&&!project.empty()&&!busy()&&uncertain.empty()&&post("newThread",Json::obj({{"project",Json(project)}}),true);}
    bool resume(size_t i){
        if(busy()||!uncertain.empty()||i>=threads.size())return false;
        auto id=threads[i].at("id").str();if(id.empty()||id.size()>160)return false;
        return post("resume",Json::obj({{"project",Json(project)},{"thread",Json(id)}}),true);
    }
    bool send() {
        if(!can_send()||draft.empty()||draft.size()>16000||!valid_utf8(draft))return false;
        auto d=scope();d.object["text"]=Json(draft);
        if(!post("send",d,true))return false;
        stale=true;notice="Задание отправляется...";return true;
    }
    bool refresh(){return ready&&!thread.empty()&&post("snapshot",scope());}
    bool interrupt(){return ready&&!thread.empty()&&post("interrupt",scope(),true);}
    bool decide(const std::string& ticket,bool accept) {
        if(!ready||stale||has("approval"))return false;
        bool found=false;for(const auto& a:view.at("approvals").array)if(a.at("id").str()==ticket)found=true;
        if(!found)return false;
        auto data=scope();data.object["approvalId"]=Json(ticket);data.object["decision"]=Json(accept?"accept":"decline");
        return post("approval",data,true);
    }
    bool reconcile(){return !uncertain.empty()&&post("requestStatus",Json::obj({{"requestId",Json(uncertain)}}));}
    void suspend(){
        ++revision;
        for(const auto& p:pending)if(p.second.operation!="requestStatus")mark_uncertain(p.second);
        net.cancel();pending.clear();stale=true;notice="Пауза. Обновите состояние; задания не повторяются.";
    }
    void disconnect(){++revision;net.cancel();pending.clear();std::fill(token.begin(),token.end(),0);token.clear();ready=false;stale=true;projects.clear();threads.clear();project.clear();thread.clear();view=Json::obj();unresolved.clear();uncertain.clear();next_cursor.clear();notice="Отключено. Активные задачи на ПК могли продолжиться.";}
};
} // namespace cv
