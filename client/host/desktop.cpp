// Desktop renderer uses the SAME Ui/Session as Vita. It is not a hardware emulator.
// --capture creates explicitly labelled fixture screenshots; never uses a model.
#include "../shared/ui.hpp"
#include <SDL.h>
#include <SDL_ttf.h>
#include <filesystem>
#include <iostream>
#include <map>

struct Renderer {
    SDL_Window* window=nullptr;SDL_Renderer* renderer=nullptr;
    std::map<int,TTF_Font*> fonts;std::string font_path;
    explicit Renderer(const std::string& path):font_path(path){
        if(SDL_Init(SDL_INIT_VIDEO)!=0||TTF_Init()!=0)throw std::runtime_error("SDL initialization failed");
        window=SDL_CreateWindow("Codex Vita - desktop test client, NOT Vita emulator",SDL_WINDOWPOS_CENTERED,SDL_WINDOWPOS_CENTERED,960,544,0);
        if(window)renderer=SDL_CreateRenderer(window,-1,SDL_RENDERER_SOFTWARE);
        if(!renderer)throw std::runtime_error("SDL renderer unavailable");
    }
    ~Renderer(){for(auto& f:fonts)TTF_CloseFont(f.second);if(renderer)SDL_DestroyRenderer(renderer);if(window)SDL_DestroyWindow(window);TTF_Quit();SDL_Quit();}
    TTF_Font* font(int size){auto& f=fonts[size];if(!f)f=TTF_OpenFont(font_path.c_str(),size);if(!f)throw std::runtime_error("Provide a readable local font using --font");return f;}
    float measure(const std::string& text,int size){int w=0,h=0;if(!text.empty()&&TTF_SizeUTF8(font(size),text.c_str(),&w,&h)!=0)throw std::runtime_error("Font measurement failed");return float(w);}
    static SDL_Color color(unsigned c){return {Uint8(c>>16),Uint8(c>>8),Uint8(c),255};}
    void box(cv::Rect b,unsigned c){auto v=color(c);SDL_SetRenderDrawColor(renderer,v.r,v.g,v.b,255);SDL_Rect r{b.x,b.y,b.w,b.h};SDL_RenderFillRect(renderer,&r);}
    void label(int x,int y,const std::string& value,unsigned c,int size){
        if(value.empty())return;
        SDL_Surface* surface=TTF_RenderUTF8_Blended(font(size),value.c_str(),color(c));if(!surface)throw std::runtime_error("Text rendering failed");
        SDL_Texture* texture=SDL_CreateTextureFromSurface(renderer,surface);SDL_Rect dst{x,y-TTF_FontAscent(font(size)),surface->w,surface->h};SDL_FreeSurface(surface);
        if(!texture)throw std::runtime_error("Text texture failed");
        SDL_RenderCopy(renderer,texture,nullptr,&dst);SDL_DestroyTexture(texture);
    }
    void draw(const cv::Scene& scene,int focus,bool fixture){
        box({0,0,960,544},cv::Background);
        for(const auto& p:scene.panels)box(p.first,p.second);
        for(size_t i=0;i<scene.buttons.size();++i){const auto& b=scene.buttons[i];box(b.rect,b.enabled?(int(i)==focus?cv::Accent:0x243447):0x1b232c);label(b.rect.x+12,b.rect.y+26,b.title,b.enabled&&int(i)==focus?cv::Background:cv::Muted,18);}
        for(const auto& t:scene.text){if(fixture&&t.x==570&&t.y==35)continue;label(t.x,t.y,t.value,t.color,t.size);}
        if(fixture)label(500,35,"TEST FIXTURE / NO CODEX / NO VITA",cv::Warning,17);
    }
    void save(const std::filesystem::path& path){
        SDL_Surface* image=SDL_CreateRGBSurfaceWithFormat(0,960,544,32,SDL_PIXELFORMAT_ARGB8888);if(!image)throw std::runtime_error("Capture allocation failed");
        if(SDL_RenderReadPixels(renderer,nullptr,SDL_PIXELFORMAT_ARGB8888,image->pixels,image->pitch)!=0||SDL_SaveBMP(image,path.string().c_str())!=0){SDL_FreeSurface(image);throw std::runtime_error("Capture failed");}SDL_FreeSurface(image);
    }
};
void fixture(cv::Session& s){
    s.ready=true;s.stale=false;s.project="test-project";s.thread="fixture-thread";s.notice="ТЕСТОВЫЕ ДАННЫЕ. Скриншот компьютерного рендера, не Vita.";
    s.endpoint="https://192.168.1.10:8765";s.ca_file="public-ca.pem";
    s.projects={cv::Json::obj({{"id",cv::Json("test-project")},{"name",cv::Json("Тестовый проект")}})};
    s.threads={cv::Json::obj({{"id",cv::Json("fixture-thread")},{"name",cv::Json("Проверка интерфейса без модели")}})};
    s.view=cv::Json::obj({{"status",cv::Json("completed")},{"messages",cv::Json::list({
        cv::Json::obj({{"role",cv::Json("user")},{"text",cv::Json("Проверь тестовый проект и покажи изменения.")}}),
        cv::Json::obj({{"role",cv::Json("assistant")},{"text",cv::Json("Это пример для проверки интерфейса. Реальный Codex не запускался.")}})})},
        {"diff",cv::Json("--- a/example.ts\n+++ b/example.ts\n-const balance = Number(value);\n+const balance = BigInt(value);\n\nТестовый diff. Файлы не изменялись.")},
        {"approvals",cv::Json::list({cv::Json::obj({{"id",cv::Json("fixture-approval")},{"details",cv::Json("{\n  \"command\": \"echo test-fixture\",\n  \"note\": \"Не выполняется\"\n}")}})})}});
}
int main(int argc,char** argv){
    std::string font_path,endpoint,ca,capture;
    for(int i=1;i+1<argc;i+=2){std::string key=argv[i];if(key=="--font")font_path=argv[i+1];else if(key=="--endpoint")endpoint=argv[i+1];else if(key=="--ca")ca=argv[i+1];else if(key=="--capture")capture=argv[i+1];else return 2;}
    if(font_path.empty()){std::cerr<<"Use --font path-to-local-font [--endpoint https://IPv4:port --ca public-ca.pem] [--capture directory]\n";return 2;}
    try{
        Renderer r(font_path);cv::Session s;cv::Ui ui;s.endpoint=endpoint;s.ca_file=ca;
        auto measure=[&](const std::string& t,int size){return r.measure(t,size);};
        if(!capture.empty()){
            fixture(s);std::filesystem::create_directories(capture);
            for(int i=0;i<6;++i){ui.jump(static_cast<cv::Page>(i));auto scene=ui.draw(s,measure);r.draw(scene,ui.focus,true);r.save(std::filesystem::path(capture)/(std::to_string(i)+".bmp"));SDL_RenderPresent(r.renderer);}
            std::cout<<"Six desktop fixture captures; NOT device screenshots\n";return 0;
        }
        bool running=true;cv::Input input=cv::Input::None;std::string buffer;
        Uint32 last=SDL_GetTicks(),next_poll=0;
        auto activate=[&](const cv::Button& b,bool held=false){auto kind=ui.activate(s,b,held);if(kind!=cv::Input::None){input=kind;buffer=kind==cv::Input::Draft?s.draft:kind==cv::Input::Endpoint?s.endpoint:"";SDL_StartTextInput();}if(b.command==cv::Command::Mic){ui.mic_requested=false;s.notice="Микрофонный индикатор доступен только на Vita";}};
        while(running){
            Uint32 now=SDL_GetTicks();unsigned elapsed=std::min(100u,now-last);last=now;s.poll();if(now>=next_poll){s.refresh();next_poll=now+750;}
            auto scene=ui.draw(s,measure);SDL_Event e;
            while(SDL_PollEvent(&e)){
                if(e.type==SDL_QUIT){running=false;continue;}
                if(e.type==SDL_WINDOWEVENT&&e.window.event==SDL_WINDOWEVENT_FOCUS_LOST){s.suspend();ui.hold.select_accept(false);}
                if(input!=cv::Input::None){
                    if(e.type==SDL_TEXTINPUT&&buffer.size()+std::char_traits<char>::length(e.text.text)<=16000)buffer+=e.text.text;
                    if(e.type==SDL_KEYDOWN){if(e.key.keysym.sym==SDLK_RETURN){ui.apply_text(s,input,buffer);std::fill(buffer.begin(),buffer.end(),0);buffer.clear();input=cv::Input::None;SDL_StopTextInput();}else if(e.key.keysym.sym==SDLK_ESCAPE){buffer.clear();input=cv::Input::None;SDL_StopTextInput();}else if(e.key.keysym.sym==SDLK_BACKSPACE&&!buffer.empty()){size_t n=buffer.size()-1;while(n&&(static_cast<unsigned char>(buffer[n])&0xc0)==0x80)--n;buffer.resize(n);}}
                    continue;
                }
                if(e.type==SDL_MOUSEWHEEL){ui.scroll=std::clamp(ui.scroll-e.wheel.y*56,0,ui.max_scroll);ui.hold.select_accept(false);}
                if(e.type==SDL_KEYDOWN&&!e.key.repeat){
                    auto k=e.key.keysym.sym;
                    if(k>=SDLK_F1&&k<=SDLK_F6)ui.jump(static_cast<cv::Page>(k-SDLK_F1));
                    else if(k==SDLK_ESCAPE){if(ui.page==cv::Page::Projects){ui.threads_mode=false;ui.list_selected=0;}else ui.jump(cv::Page::Projects);}
                    else if(k==SDLK_TAB&&!scene.buttons.empty())ui.focus=(ui.focus+1)%int(scene.buttons.size());
                    else if(k==SDLK_UP||k==SDLK_DOWN){int d=k==SDLK_DOWN?1:-1;if(ui.page==cv::Page::Projects){auto n=ui.threads_mode?s.threads.size():s.projects.size();if(n){ui.list_selected=std::clamp(ui.list_selected+d,0,int(n)-1);ui.focus=ui.list_selected%5;}}else ui.scroll=std::clamp(ui.scroll+d*28,0,ui.max_scroll);}
                    else if(k==SDLK_RETURN&&!scene.buttons.empty())activate(scene.buttons[size_t(ui.focus)]);
                }
                if(e.type==SDL_MOUSEBUTTONDOWN){for(int i=0;i<6;++i)if(cv::inside({16+156*i,58,148,40},e.button.x,e.button.y))ui.jump(static_cast<cv::Page>(i));for(size_t i=0;i<scene.buttons.size();++i)if(cv::inside(scene.buttons[i].rect,e.button.x,e.button.y)){ui.focus=int(i);activate(scene.buttons[i]);}}
            }
            scene=ui.draw(s,measure);
            if(input==cv::Input::None&&!scene.buttons.empty()&&scene.buttons[size_t(ui.focus)].hold&&scene.buttons[size_t(ui.focus)].enabled){if(!ui.hold.accept_selected)ui.hold.select_accept(true);if(ui.hold.update(SDL_GetKeyboardState(nullptr)[SDL_SCANCODE_RETURN]!=0,elapsed))activate(scene.buttons[size_t(ui.focus)],true);}else ui.hold.select_accept(false);
            r.draw(scene,ui.focus,false);
            if(input!=cv::Input::None){r.box({16,120,928,342},0x243447);r.label(32,155,"Ввод: Enter — подтвердить, Esc — отменить",cv::Accent,20);auto lines=cv::wrap(buffer,870.0f,[&](const std::string& t){return r.measure(t,20);});int y=192;for(const auto& line:lines){if(y>438)break;r.label(32,y,line,cv::Foreground,20);y+=28;}}
            SDL_RenderPresent(r.renderer);SDL_Delay(10);
        }
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
